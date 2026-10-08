"""PyInstaller entry point for the Windows exe build."""
import sys
import traceback

from srtgo.srtgo import srtgo


def main():
    try:
        srtgo()
    except Exception:
        traceback.print_exc()
        # A double-clicked exe closes its console on exit, so hold it open to show the error.
        if getattr(sys, "frozen", False):
            input("\n오류가 발생했습니다. Enter 키를 누르면 종료합니다...")
        sys.exit(1)


if __name__ == "__main__":
    main()
