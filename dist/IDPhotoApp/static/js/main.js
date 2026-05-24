let uploadId = null;
let selectedPackage = null;
let selectedBgColor = '#ffffff';
let resultId = null;

// ── Drag & drop ──────────────────────────────────────────────────────────────
const zone = document.getElementById('upload-zone');
zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
zone.addEventListener('drop', e => {
  e.preventDefault(); zone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});
document.getElementById('file-input').addEventListener('change', e => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
});

function handleFile(file) {
  if (!file.type.startsWith('image/')) { showToast('Please upload an image file.', 'error'); return; }
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('preview-img').src = e.target.result;
    document.getElementById('mini-preview').src = e.target.result;
    zone.style.display = 'none';
    document.getElementById('preview-wrap').style.display = 'block';
    document.getElementById('step1-next').style.display = 'block';
    document.getElementById('upload-thumb-mini').style.display = 'block';
  };
  reader.readAsDataURL(file);
  uploadFile(file);
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append('photo', file);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { showToast(data.error, 'error'); return; }
    uploadId = data.upload_id;
  } catch(e) { showToast('Upload failed. Try again.', 'error'); }
}

function resetUpload() {
  uploadId = null;
  document.getElementById('file-input').value = '';
  document.getElementById('preview-img').src = '';
  zone.style.display = 'block';
  document.getElementById('preview-wrap').style.display = 'none';
  document.getElementById('step1-next').style.display = 'none';
}

function goStep2() {
  if (!uploadId) { showToast('Please wait for upload to finish.', 'error'); return; }
  showPanel('panel-options');
  setStep(2);
}

// ── Package selection ─────────────────────────────────────────────────────────
function selectPackage(pid, el) {
  document.querySelectorAll('.pkg-card').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  selectedPackage = pid;
  updateProcessBtn();
}

function updateProcessBtn() {
  document.getElementById('process-btn').disabled = !(uploadId && selectedPackage);
}

// ── Background options ────────────────────────────────────────────────────────
function toggleBgOptions() {
  const on = document.getElementById('toggle-bg').checked;
  document.getElementById('bg-options').style.display = on ? 'block' : 'none';
}

function pickBgColor(color, el) {
  selectedBgColor = color;
  document.getElementById('bg-color-picker').value = color;
  document.getElementById('bg-color-val').textContent = color;
  document.querySelectorAll('.bg-swatch').forEach(s => s.classList.remove('active'));
  if (el) el.classList.add('active');
}

function bgPickerChange(color) {
  selectedBgColor = color;
  document.getElementById('bg-color-val').textContent = color;
  document.querySelectorAll('.bg-swatch').forEach(s => s.classList.remove('active'));
}

// ── Process ───────────────────────────────────────────────────────────────────
async function processPhoto() {
  if (!uploadId || !selectedPackage) { showToast('Select a package first.', 'error'); return; }
  const replaceBg = document.getElementById('toggle-bg').checked;

  showProgress('Detecting face & cropping…');
  try {
    const res = await fetch('/api/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        upload_id: uploadId,
        package_id: selectedPackage,
        replace_background: replaceBg,
        background_color: selectedBgColor
      })
    });
    const data = await res.json();
    hideProgress();
    if (data.error) { showToast(data.error, 'error'); return; }
    resultId = data.result_id;
    showResult(data.preview_url);
  } catch(e) {
    hideProgress();
    showToast('Processing failed. Please try again.', 'error');
  }
}

function showResult(url) {
  document.getElementById('result-img').src = url + '?t=' + Date.now();
  document.getElementById('result-section').style.display = 'block';
  document.getElementById('result-section').scrollIntoView({ behavior: 'smooth' });
  setStep(3);
}

function download(fmt) {
  if (!resultId) return;
  window.location = `/api/download/${resultId}/${fmt}`;
}

function startOver() {
  resetUpload();
  showPanel('panel-upload');
  setStep(1);
  selectedPackage = null;
  resultId = null;
  document.getElementById('result-section').style.display = 'none';
  document.querySelectorAll('.pkg-card').forEach(c => c.classList.remove('selected'));
  document.getElementById('toggle-bg').checked = false;
  document.getElementById('bg-options').style.display = 'none';
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showPanel(id) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function setStep(n) {
  for (let i = 1; i <= 3; i++) {
    const el = document.getElementById(`step${i}-ind`);
    el.classList.remove('active', 'done');
    if (i < n) el.classList.add('done');
    else if (i === n) el.classList.add('active');
  }
}

function showProgress(msg) {
  document.getElementById('progress-text').textContent = msg || 'Processing…';
  document.getElementById('progress-overlay').classList.add('show');
}
function hideProgress() {
  document.getElementById('progress-overlay').classList.remove('show');
}

let toastTimer;
function showToast(msg, type = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (type ? ' ' + type : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3500);
}