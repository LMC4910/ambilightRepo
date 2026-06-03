import sys

def main():
    print("Testing imports for PyInstaller packaging...")

    try:
        import mss
        print("mss OK")
    except ImportError as e:
        print(f"mss failed: {e}")

    try:
        import dxcam
        cam = dxcam.create()
        print("dxcam OK")
    except ImportError as e:
        print(f"dxcam failed: {e}")
    except Exception as e:
        print(f"dxcam initialized with error: {e}")

    try:
        import cupy as cp
        arr = cp.zeros((100, 100))
        print("cupy OK")
    except ImportError as e:
        print(f"cupy failed: {e}")
    except Exception as e:
        print(f"cupy initialized with error: {e}")

    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
