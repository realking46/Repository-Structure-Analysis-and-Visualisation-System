# Backend

FastAPI service that scans local repositories and returns graph data for the frontend.

Run from this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows, use a Windows Python distribution for the virtualenv. MSYS/MinGW Python may fail to install packages that publish native wheels.

You can also start the backend with `run-dev.bat` after installing dependencies.

Run backend tests with:

```powershell
.\run-tests.bat
```

The analyzer does static parsing only. It never imports or executes scanned project code.
