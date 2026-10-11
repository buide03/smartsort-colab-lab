"""Container/hosting entrypoint; a single worker preserves the task queue and volume state."""
import os
import uvicorn

if __name__ == '__main__':
    uvicorn.run('smartsort_app.server:app',host='0.0.0.0',port=int(os.environ.get('PORT','8000')),
                workers=1,log_level='info')
