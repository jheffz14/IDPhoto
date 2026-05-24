# 📷 ID Photo Studio

A production-ready Python web application for automated ID photo resizing and print-layout generation.

---

## Project Structure

```
idphoto/
├── app.py                  # Flask application + API routes
├── image_processor.py      # Face detection, cropping, layout engine
├── requirements.txt        # Python dependencies
├── data/
│   └── config.json         # All configuration (sizes, packages, admin)
├── static/
│   ├── uploads/            # User uploaded images (auto-cleaned)
│   └── outputs/            # Generated layout images
└── templates/
    ├── index.html          # Main user interface
    ├── admin_login.html    # Admin login page
    └── admin.html          # Admin dashboard
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py

# 3. Open in browser
http://localhost:5000

# Admin panel
http://localhost:5000/admin
# Default: admin / admin123
```

---

## Configuration (data/config.json)

All settings are stored in `data/config.json`. **No database needed.**

### Admin credentials
```json
"admin": {
  "username": "admin",
  "password": "your-secure-password",
  "session_secret": "change-this-in-production"
}
```

### App settings
```json
"app": {
  "title": "ID Photo Studio",
  "logo": "📷",
  "upload_max_mb": 20,
  "output_dpi": 300
}
```

### Photo sizes
Each size has: `name`, `width_mm`, `height_mm`, `background_color`, `enabled`

### Packages
Each package has: `name`, `description`, `enabled`, `items[]`, `paper_size`, `orientation`, `margin_mm`, `spacing_mm`, `show_cut_lines`, `background_color`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload a photo |
| POST | `/api/process` | Process photo with a package |
| GET | `/api/download/<id>/<fmt>` | Download result (png/jpeg/pdf) |
| GET | `/api/config/public` | Get public config |
| POST | `/admin/login` | Admin login |
| GET | `/api/admin/config` | Get full config (admin) |
| POST | `/api/admin/config` | Update app/paper settings (admin) |
| POST | `/api/admin/photo_sizes` | Create photo size (admin) |
| PUT | `/api/admin/photo_sizes/<id>` | Update photo size (admin) |
| DELETE | `/api/admin/photo_sizes/<id>` | Delete photo size (admin) |
| POST | `/api/admin/packages` | Create package (admin) |
| PUT | `/api/admin/packages/<id>` | Update package (admin) |
| DELETE | `/api/admin/packages/<id>` | Delete package (admin) |

---

## Libraries Used

| Library | Purpose |
|---------|---------|
| Flask | Web framework |
| Pillow | Image manipulation, composition |
| OpenCV (headless) | Face detection (Haar cascades) |
| ReportLab | PDF generation |
| NumPy | Array operations for image processing |
| Werkzeug | Secure file handling |

---

## Features

### User Features
- Drag & drop photo upload
- Automatic face detection & smart crop
- EXIF orientation correction
- Package selection (configurable)
- Optional background replacement (GrabCut algorithm)
- Custom background color picker
- Preview before download
- Download as PNG, JPEG, or PDF

### Admin Features
- Photo size CRUD (name, dimensions, background)
- Package builder (multiple sizes, quantities per package)
- Paper size management (A4, Letter, 4R, custom)
- Layout settings (margins, spacing, cut lines, orientation)
- App settings (title, logo, DPI, upload limits)
- Password change
- All data persisted to `config.json`

---

## Deployment

### Development
```bash
python app.py  # runs on localhost:5000
```

### Production (Gunicorn + Nginx)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

**Nginx config:**
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static {
        alias /path/to/idphoto/static;
        expires 1h;
    }
}
```

### Docker
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y libglib2.0-0 libsm6 libxrender1 libxext6
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```

---

## Storage Cleanup

Uploaded and output files accumulate over time. Add a cron job:
```bash
# Delete files older than 24 hours
0 3 * * * find /path/to/idphoto/static/uploads -mtime +1 -delete
0 3 * * * find /path/to/idphoto/static/outputs -mtime +1 -delete
```

---

## Security Notes

1. **Change the admin password** immediately after first login
2. **Change `session_secret`** in config.json to a long random string
3. Consider adding HTTPS via Let's Encrypt for production
4. The upload directory should not be accessible via direct URL in production (move outside `static/`)
