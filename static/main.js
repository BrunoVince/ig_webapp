// main.js für Bild-Upload, Drag & Drop, Vorschau und Fehler-Handling

// Hier wird später der Code für die Bildvorschau und Drag & Drop ergänzt. 

// Button nur auf mobilen Geräten anzeigen
function isMobile() {
    return /Android|iPhone|iPad|iPod|Opera Mini|IEMobile|WPDesktop/i.test(navigator.userAgent);
}
const shareBtn = document.getElementById('share-instagram');
if (shareBtn && isMobile() && navigator.canShare) {
    shareBtn.style.display = 'block';
    shareBtn.addEventListener('click', async function(e) {
        e.preventDefault();
        try {
            const response = await fetch(shareBtn.getAttribute('data-result-url'));
            const blob = await response.blob();
            const file = new File([blob], shareBtn.getAttribute('data-filename'), { type: blob.type });
            await navigator.share({
                files: [file],
                title: 'Bild für Instagram',
                text: 'Hier ist mein neues Bild!'
            });
        } catch (err) {
            showError('Teilen nicht möglich. Bitte Bild herunterladen und manuell posten.');
        }
    });
}

// Bootstrap-Alert für Fehler
function showError(msg) {
    let alert = document.getElementById('main-error-alert');
    if (!alert) {
        alert = document.createElement('div');
        alert.id = 'main-error-alert';
        alert.className = 'alert alert-danger mt-3';
        const form = document.querySelector('form');
        form.parentNode.insertBefore(alert, form);
    }
    alert.textContent = msg;
    alert.style.display = 'block';
    setTimeout(() => { alert.style.display = 'none'; }, 5000);
}

// Darkmode Toggle
const darkToggle = document.getElementById('darkmode-toggle');
if (darkToggle) {
    // Initial: System-Theme oder gespeicherte Präferenz
    const userPref = localStorage.getItem('theme');
    if (userPref) {
        document.body.setAttribute('data-theme', userPref);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.body.setAttribute('data-theme', 'dark');
    }
    darkToggle.addEventListener('click', () => {
        const current = document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.body.setAttribute('data-theme', current);
        localStorage.setItem('theme', current);
    });
}

const imageInput = document.getElementById('image');
const imagePreview = document.getElementById('image-preview');
imageInput.addEventListener('change', function() {
    imagePreview.innerHTML = '';
    if (this.files && this.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = document.createElement('img');
            img.src = e.target.result;
            img.className = 'preview-img';
            imagePreview.appendChild(img);
        };
        reader.readAsDataURL(this.files[0]);
    }
});

// --- BEGIN: Live Preview Overlay Block ---
// --- END: Live Preview Overlay Block --- 