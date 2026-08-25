import cv2
import time

DEVICE = 0
WIDTH = 640
HEIGHT = 360
FPS = 260
TEST_SECONDS = 10

cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, FPS)

print("Requested:")
print(f"  {WIDTH}x{HEIGHT} @ {FPS} fps MJPG")

print("Actual OpenCV settings:")
print(f"  Width:  {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}")
print(f"  Height: {cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
print(f"  FPS:    {cap.get(cv2.CAP_PROP_FPS)}")
print()

if not cap.isOpened():
    raise RuntimeError("Could not open camera")

intervals = []

# Throw away a few frames while the camera settles.
for _ in range(20):
    cap.read()

print(f"Timing frames for {TEST_SECONDS} seconds...")

start = time.perf_counter()
previous = None
frame_count = 0

while time.perf_counter() - start < TEST_SECONDS:
    ok, frame = cap.read()

    now = time.perf_counter()

    if not ok:
        print("READ FAILED")
        continue

    if previous is not None:
        intervals.append((now - previous) * 1000.0)

    previous = now
    frame_count += 1

cap.release()

print()
print(f"Frames read: {frame_count}")
print(f"Measured FPS: {frame_count / TEST_SECONDS:.2f}")

if intervals:
    print(f"Minimum interval: {min(intervals):.3f} ms")
    print(f"Maximum interval: {max(intervals):.3f} ms")

    over_5 = [x for x in intervals if x > 5]
    over_10 = [x for x in intervals if x > 10]
    over_15 = [x for x in intervals if x > 15]

    print(f"Intervals > 5 ms:  {len(over_5)}")
    print(f"Intervals > 10 ms: {len(over_10)}")
    print(f"Intervals > 15 ms: {len(over_15)}")

    print()
    print("Intervals > 10 ms:")

    for i, dt in enumerate(intervals):
        if dt > 10:
            print(f"  frame {i + 1}: {dt:.3f} ms")