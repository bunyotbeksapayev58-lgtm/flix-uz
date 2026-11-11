import os
import sys
import glob
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def verify_all_callbacks():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = glob.glob(os.path.join(base_dir, "handlers", "*.py")) + glob.glob(os.path.join(base_dir, "keyboards", "*.py"))
    cbs = set()
    for f in files:
        with open(f, encoding="utf-8") as fp:
            for m in re.finditer(r'callback_data=["\']([^"\']+)["\']', fp.read()):
                cbs.add(m.group(1))

    handler_files = glob.glob(os.path.join(base_dir, "handlers", "*.py"))
    all_handler_code = "\n".join(open(f, encoding="utf-8").read() for f in handler_files)

    missing = []
    for c in sorted(cbs):
        # check exact match, prefix match or regex
        prefix = c.split(":")[0] + ":" if ":" in c else c
        if c in all_handler_code:
            continue
        if prefix in all_handler_code:
            continue
        missing.append(c)

    print(f"Total callbacks: {len(cbs)}")
    if missing:
        print(f"❌ MISSING HANDLERS for: {missing}")
    else:
        print("✅ ALL CALLBACKS HAVE MATCHING HANDLERS!")

if __name__ == "__main__":
    verify_all_callbacks()
