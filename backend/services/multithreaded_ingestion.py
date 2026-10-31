"""Operating Systems Module — Multithreaded Meter Reading Ingestion Service.

Architecture:
  Concurrent Meter Producers (threading.Thread)
                 ↓ (thread-safe submit)
            queue.Queue (Thread-Safe FIFO Queue)
                 ↓ (dequeued by consumer)
       Memory Buffer (Protected by threading.Lock)
                 ↓ (batch flushed on size or timeout)
       Batch Consumer / Writer (threading.Thread)
                 ↓ (safe SessionLocal transactions)
           SQLite Database (energywatch.db)

Features:
- Demonstrable Producer-Consumer synchronization.
- Non-blocking to FastAPI event loop.
- Batch database insertion for I/O efficiency.
- Safe SQLAlchemy session lifecycle per batch.
- Deduplication against database to preserve data integrity.
- Graceful shutdown with buffer flushing.
- Full telemetry instrumentation (queued, processed, duplicates skipped, failed).
"""
from datetime import datetime, timedelta, timezone
import logging
import math
import queue
import random
import threading
import time
from typing import Any, Dict, List, Optional

from backend.database import SessionLocal
from backend.models import MeterReading

logger = logging.getLogger("energywatch.ingestion")


class MultithreadedIngestionManager:
    """Thread-safe ingestion manager implementing producer-consumer meter logging."""

    def __init__(self, batch_size: int = 10, batch_timeout_seconds: float = 1.5):
        self.batch_size = batch_size
        self.batch_timeout_seconds = batch_timeout_seconds

        # 1. Thread-Safe FIFO Queue
        self.reading_queue: queue.Queue = queue.Queue(maxsize=2000)

        # 2. In-Memory Batch Buffer
        self.memory_buffer: List[Dict[str, Any]] = []
        self.buffer_lock = threading.Lock()

        # 3. Telemetry Statistics
        self.stats_lock = threading.Lock()
        self.total_submitted: int = 0
        self.total_processed: int = 0
        self.total_duplicates_skipped: int = 0
        self.total_failed: int = 0
        self.batches_written: int = 0
        self.last_batch_time: Optional[datetime] = None

        # 4. Lifecycle Control
        self.stop_event = threading.Event()
        self.consumer_thread: Optional[threading.Thread] = None
        self.active_producers: List[threading.Thread] = []

        self._ensure_consumer_running()

    def _ensure_consumer_running(self):
        """Ensure background batch consumer thread is active."""
        if self.consumer_thread is None or not self.consumer_thread.is_alive():
            self.stop_event.clear()
            self.consumer_thread = threading.Thread(
                target=self._consumer_worker,
                name="EnergyWatch-BatchConsumer",
                daemon=True,
            )
            self.consumer_thread.start()

    def submit_reading(self, reading_data: Dict[str, Any], block: bool = True, timeout: float = 2.0) -> bool:
        """Submit a raw smart meter reading dictionary into the thread-safe queue."""
        self._ensure_consumer_running()
        try:
            self.reading_queue.put(reading_data, block=block, timeout=timeout)
            with self.stats_lock:
                self.total_submitted += 1
            return True
        except queue.Full:
            with self.stats_lock:
                self.total_failed += 1
            logger.error("Reading queue is full. Ingestion dropped.")
            return False

    def _consumer_worker(self):
        """Background daemon thread: consumes from queue, buffers, and writes in batches."""
        last_flush_time = time.time()

        while not self.stop_event.is_set() or not self.reading_queue.empty():
            try:
                # Wait for next item up to 0.4s to permit periodic timeout checks
                reading = self.reading_queue.get(timeout=0.4)
                with self.buffer_lock:
                    self.memory_buffer.append(reading)
                self.reading_queue.task_done()
            except queue.Empty:
                pass

            now = time.time()
            time_since_flush = now - last_flush_time

            # Trigger batch write if threshold reached or timeout elapsed
            with self.buffer_lock:
                buffer_len = len(self.memory_buffer)

            if buffer_len >= self.batch_size or (buffer_len > 0 and time_since_flush >= self.batch_timeout_seconds):
                self._flush_buffer_to_database()
                last_flush_time = time.time()

        # Final drain on shutdown
        self._flush_buffer_to_database()

    def _flush_buffer_to_database(self):
        """Commit currently buffered readings to SQLite database within a safe session."""
        with self.buffer_lock:
            if not self.memory_buffer:
                return
            items_to_write = list(self.memory_buffer)
            self.memory_buffer.clear()

        session = SessionLocal()
        inserted_count = 0
        skipped_count = 0
        failed_count = 0

        try:
            readings_to_add: List[MeterReading] = []
            seen_in_batch = set()

            for item in items_to_write:
                try:
                    meter_id = str(item.get("meter_id", "EW-2847-HH")).strip()
                    raw_ts = item.get("timestamp")
                    if isinstance(raw_ts, str):
                        try:
                            ts = datetime.fromisoformat(raw_ts.replace("Z", ""))
                        except ValueError:
                            ts = datetime.now()
                    elif isinstance(raw_ts, datetime):
                        ts = raw_ts
                    else:
                        ts = datetime.now()

                    kwh = float(item.get("usage_kwh", 0.0))
                    if math.isnan(kwh) or kwh < 0:
                        failed_count += 1
                        continue

                    # Batch-level deduplication
                    batch_key = (meter_id, ts)
                    if batch_key in seen_in_batch:
                        skipped_count += 1
                        continue
                    seen_in_batch.add(batch_key)

                    # Database-level deduplication
                    exists = (
                        session.query(MeterReading.id)
                        .filter(
                            MeterReading.meter_id == meter_id,
                            MeterReading.timestamp == ts,
                        )
                        .first()
                    )
                    if exists:
                        skipped_count += 1
                        continue

                    volt = float(item.get("voltage_v", 230.0))
                    pf = float(item.get("power_factor", 0.96))
                    current = item.get("current_a")
                    if current is None:
                        current = round((kwh * 1000.0) / (volt * pf), 1) if (volt * pf > 0) else 0.0
                    else:
                        current = float(current)

                    status = item.get("status", "Normal")
                    source = item.get("source", "simulated")
                    reading_type = item.get("reading_type", "hourly")

                    reading_obj = MeterReading(
                        meter_id=meter_id,
                        timestamp=ts,
                        usage_kwh=round(kwh, 2),
                        voltage_v=round(volt, 1),
                        current_a=round(current, 1),
                        power_factor=round(pf, 2),
                        status=status,
                        source=source,
                        reading_type=reading_type,
                    )
                    readings_to_add.append(reading_obj)
                except Exception as ex:
                    logger.warning(f"Failed to parse stream reading: {ex}")
                    failed_count += 1

            if readings_to_add:
                session.add_all(readings_to_add)
                session.commit()
                inserted_count = len(readings_to_add)

            with self.stats_lock:
                self.total_processed += inserted_count
                self.total_duplicates_skipped += skipped_count
                self.total_failed += failed_count
                self.batches_written += 1
                self.last_batch_time = datetime.now()

        except Exception as e:
            session.rollback()
            logger.error(f"Error executing batch database write: {e}")
            with self.stats_lock:
                self.total_failed += len(items_to_write)
        finally:
            session.close()

    def start_concurrent_simulation(
        self,
        num_producers: int = 3,
        readings_per_producer: int = 8,
        interval_seconds: float = 0.05,
    ) -> Dict[str, Any]:
        """Launch multiple concurrent Producer threads to demonstrate multithreading & queue ingestion."""
        self._ensure_consumer_running()

        producer_threads: List[threading.Thread] = []

        def producer_worker(producer_idx: int, meter_name: str):
            rng = random.Random(100 + producer_idx * 17)
            # Anchor to a distinctive demonstration minute so they don't collide with existing hours
            base_time = datetime(2026, 10, 31, 14, 0, 0) + timedelta(minutes=producer_idx * 10)

            for step in range(readings_per_producer):
                if self.stop_event.is_set():
                    break

                ts = base_time + timedelta(minutes=step)
                hour = ts.hour
                base_kwh = 1.2 if 8 <= hour <= 20 else 0.4
                noise = rng.uniform(0.9, 1.1)
                kwh = round(base_kwh * noise, 2)
                volt = round(rng.uniform(228.0, 234.0), 1)
                pf = round(rng.uniform(0.95, 0.98), 2)
                curr = round((kwh * 1000.0) / (volt * pf), 1)

                reading_payload = {
                    "meter_id": meter_name,
                    "timestamp": ts,
                    "usage_kwh": kwh,
                    "voltage_v": volt,
                    "current_a": curr,
                    "power_factor": pf,
                    "status": "Normal",
                    "source": "simulated",
                    "reading_type": "hourly",
                }

                self.submit_reading(reading_payload)
                time.sleep(interval_seconds)

        for i in range(num_producers):
            m_id = f"EW-STREAM-{i+1:02d}"
            t = threading.Thread(
                target=producer_worker,
                args=(i, m_id),
                name=f"ProducerThread-{i+1}-{m_id}",
                daemon=True,
            )
            producer_threads.append(t)
            t.start()

        self.active_producers = [t for t in producer_threads if t.is_alive()]

        return {
            "status": "started",
            "producers_launched": num_producers,
            "readings_per_producer": readings_per_producer,
            "expected_total_readings": num_producers * readings_per_producer,
            "message": f"Successfully spawned {num_producers} concurrent producer threads submitting to thread-safe queue.",
        }

    def flush(self) -> None:
        """Immediately drain reading queue and flush memory buffer to database."""
        # Drain items from queue into buffer
        while not self.reading_queue.empty():
            try:
                r = self.reading_queue.get_nowait()
                with self.buffer_lock:
                    self.memory_buffer.append(r)
                self.reading_queue.task_done()
            except queue.Empty:
                break
        self._flush_buffer_to_database()

    def get_statistics(self) -> Dict[str, Any]:
        """Return real-time operational status and telemetry for producer-consumer system."""
        with self.stats_lock:
            tot_sub = self.total_submitted
            tot_proc = self.total_processed
            tot_dup = self.total_duplicates_skipped
            tot_fail = self.total_failed
            b_written = self.batches_written
            last_bt = self.last_batch_time.isoformat() if self.last_batch_time else None

        with self.buffer_lock:
            buf_size = len(self.memory_buffer)

        q_size = self.reading_queue.qsize()
        active_prod_count = sum(1 for t in self.active_producers if t.is_alive())
        consumer_alive = bool(self.consumer_thread and self.consumer_thread.is_alive())

        return {
            "architecture": "Producer-Consumer Pipeline (threading.Thread + queue.Queue + Batch Memory Buffer)",
            "consumer_status": "active" if consumer_alive else "stopped",
            "queue_current_size": q_size,
            "memory_buffer_size": buf_size,
            "batch_capacity": self.batch_size,
            "active_producer_threads": active_prod_count,
            "total_submitted": tot_sub,
            "total_processed": tot_proc,
            "total_duplicates_skipped": tot_dup,
            "total_failed": tot_fail,
            "batches_written": b_written,
            "last_batch_time": last_bt,
            "thread_safety": "threading.Lock and queue.Queue",
        }

    def shutdown(self, timeout: float = 3.0):
        """Clean shutdown: signal threads to stop and flush all buffered items."""
        self.stop_event.set()
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=timeout)
        self.flush()


# Global Singleton Instance for EnergyWatch Application
ingestion_manager = MultithreadedIngestionManager()

