"""Start the MAWOS backend API.  The React app runs separately via Vite."""
import uvicorn

if __name__ == "__main__":
    print("MAWOS backend API: http://127.0.0.1:8000")
    print("API documentation: http://127.0.0.1:8000/docs")
    print("React frontend: cd frontend && npm run dev (http://127.0.0.1:5173)")
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=False)
