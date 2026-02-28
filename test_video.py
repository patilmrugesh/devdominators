import cv2, os, sys
path = r"videoplayback.mp4"
print("File exists:", os.path.isfile(path))
print("File size:", os.path.getsize(path) // (1024*1024), "MB")
cap = cv2.VideoCapture(path)
print("Opened:", cap.isOpened())
if cap.isOpened():
    ret, f = cap.read()
    print("Frame read:", ret)
    if ret:
        print("Frame shape:", f.shape)
        print("Resolution:", f.shape[1], "x", f.shape[0])
    print("Total frames:", int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    print("Video FPS:", cap.get(cv2.CAP_PROP_FPS))
    cap.release()
    print("SUCCESS: Video is valid!")
else:
    print("ERROR: Cannot open video")
    sys.exit(1)
