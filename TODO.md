# Render Deployment TODO

## Steps Completed
- [x] 1. Analyzed files for localhost:5000 references (only in app.py local run).
- [x] 2. Created Procfile for gunicorn + eventlet (SocketIO).
- [x] 3. Created runtime.txt (python-3.12.7).
- [x] 4. Updated requirements.txt (added eventlet).
- [x] 5. Updated app.py CORS/SocketIO origins to include frontend Render URL + local.


## Pending Steps
- [x] 5. Edited app.py: Commented local run (removed localhost:5000), updated CORS/SocketIO to "*" origins.
- [x] 6. Updated routes/auth.py: Google callback redirect uses FRONTEND_URL env var (default local:5173).


- [ ] 7. Test local with gunicorn `gunicorn -k eventlet -b 0.0.0.0:8000 app:app`.
- [ ] 8. Deploy to Render.
- [ ] 5. Edit app.py: Comment local run block, update CORS/SocketIO to allow prod origins.
- [ ] 6. Edit routes/auth.py: Update Google callback redirect (needs frontend URL).
- [ ] 7. Test local with gunicorn `gunicorn -k eventlet -b 0.0.0.0:8000 app:app`.
- [ ] 8. Deploy to Render.

- [ ] 3. Update requirements.txt (add eventlet).
- [ ] 4. Edit app.py: Comment local run block, update CORS/SocketIO origins to '*' or prod frontend.
- [ ] 5. Edit routes/auth.py: Update Google callback redirect to prod frontend URL.
- [ ] 6. Create runtime.txt.
- [ ] 7. Test local with gunicorn.
- [ ] 8. Deploy to Render, set env vars.
- [ ] 9. Update frontend API/WebSocket URL to Render backend.
