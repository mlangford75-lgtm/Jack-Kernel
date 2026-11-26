"""Repeatable isolated matcher benchmark. No model, real credentials or network.

Run from repository root: python tests/benchmark_streaming_irq.py
Timing is informational, not a flaky CI performance gate. Correctness and
bounded retained text are asserted. Memory tracing runs separately from timing.
"""
from pathlib import Path
import random
import statistics
import string
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jack_evidence_guard import CanaryPattern, CanaryTier, DeterministicCanarySet, StreamingCanaryDetector


def measure(length, sensitivity, count, chunk_size):
    rng = random.Random(937)
    alphabet = string.ascii_letters + string.digits
    values = ["".join(rng.choice(alphabet) for _ in range(length)) for _ in range(count)]
    policy = DeterministicCanarySet(
        tuple(CanaryPattern("synthetic-" + str(i), CanaryTier.B, value, sensitivity)
              for i, value in enumerate(values)), max_window=16384)
    # Separate alphabet gives a guaranteed clean baseline. The adversarial
    # correctness case below uses a matching fragment from the middle.
    sample = ("!~? /+=,;" * 456)[:4096]
    chunks = [sample[i:i + chunk_size] for i in range(0, len(sample), chunk_size)]

    def run():
        detector = StreamingCanaryDetector(policy)
        released = 0
        for part in chunks:
            safe, match = detector.feed_guarded(part)
            assert match is None
            assert detector.held_length <= policy.required_window
            released += len(safe)
        released += len(detector.flush_safe())
        assert released == len(sample)

    times = []
    for _ in range(3):
        start = time.perf_counter()
        run()
        times.append(time.perf_counter() - start)
    tracemalloc.start()
    run()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    width = policy._patterns[0].match_chars
    start = (length - width) // 2
    fragment = values[0][start:start + width]
    detector = StreamingCanaryDetector(policy)
    prefix = "safe! "
    released = ""
    for part in (prefix + fragment[:width // 2], fragment[width // 2:]):
        safe, match = detector.feed_guarded(part)
        released += safe
    assert match is not None and released == prefix
    median = statistics.median(times)
    print(f"{length},{sensitivity},{count},{chunk_size},{policy.required_window},"
          f"{median * 1000:.3f},{median * 1e6 / len(chunks):.2f},{peak}")


if __name__ == "__main__":
    print("key_chars,percent,patterns,chunk_chars,held_chars,median_ms_per_4096_chars,mean_us_per_chunk,traced_peak_bytes")
    for length in (128, 256, 1024):
        for sensitivity in (5, 25, 100):
            for chunk_size in (16, 128):
                measure(length, sensitivity, 1, chunk_size)
    for count in (8, 32, 128):
        for sensitivity in (5, 25, 100):
            measure(1024, sensitivity, count, 64)
