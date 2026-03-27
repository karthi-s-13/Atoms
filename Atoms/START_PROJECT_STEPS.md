# How to Set Up and Start the Project

## 1. Create a Python Virtual Environment (first time only)

```
python -m venv .venv
```

## 2. Activate the Virtual Environment
- **Windows:**
  ```
  .\.venv\Scripts\activate
  ```
- **Mac/Linux:**
  ```
  source .venv/bin/activate
  ```

## 3. Install Backend Dependencies
```
pip install -r Atoms/realtime_server/requirements.txt
```

## 4. Start the Backend Server
```
uvicorn realtime_server.main:app --reload --host 0.0.0.0 --port 8000 --app-dir Atoms
```

## 5. Start the Frontend
Open a new terminal and run:
```
cd Atoms/frontend
npm install
npm run dev
```

## 6. Open the App
Go to [http://localhost:5173](http://localhost:5173) in your browser.

---

**Tip:**
- Steps 1 and 2 are only needed the first time (or when setting up on a new machine).
- Steps 3–6 are for every new session.
