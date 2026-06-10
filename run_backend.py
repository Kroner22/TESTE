import subprocess, sys, time, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
out = open("backend_stdout.log", "w", encoding="utf-8")
err = open("backend_stderr.log", "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"],
    stdout=out, stderr=err
)
print(f"PID: {proc.pid}")
sys.stdout.flush()
time.sleep(3)
print("Process started" if proc.poll() is None else f"Process exited: {proc.returncode}")
