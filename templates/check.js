  
    emailjs.init("mmGDeX1c3j2Bzop95");

    // ---- Maintenance Check ----
    async function checkMaintenance() {
      try {
        const res = await fetch('/api/maintenance/status');
        if (res.ok) {
          const data = await res.json();
          if (data.enabled) {
            // Overlay the entire page or redirect
            document.body.innerHTML = `
              <div class="fixed inset-0 bg-gray-900 z-[9999] flex flex-col items-center justify-center text-center p-6">
                <div class="w-24 h-24 bg-red-500/10 rounded-full flex items-center justify-center mb-6" style="animation: pulse 2s infinite">
                  <svg class="w-12 h-12 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  </svg>
                </div>
                <h1 class="text-3xl font-bold text-white mb-4">Under Maintenance</h1>
                <p class="text-gray-400 text-lg">The server is currently down for maintenance. We will be back shortly.</p>
              </div>
            `;
            // Add basic pulse animation dynamically if not present
            if (!document.getElementById('pulse-anim')) {
              const style = document.createElement('style');
              style.id = 'pulse-anim';
              style.innerHTML = `@keyframes pulse { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.05); opacity: .8; } }`;
              document.head.appendChild(style);
            }
          }
        }
      } catch (e) { console.error('Maintenance check failed', e); }
    }
    
    // Run check immediately
    checkMaintenance();

    particlesJS('particles-js', {
      particles: {
        number: { value: 80, density: { enable: true, value_area: 800 } },
        color: { value: "#4a5568" }, shape: { type: "circle" },
        opacity: { value: 0.5, random: true }, size: { value: 3, random: true },
        line_linked: { enable: true, distance: 150, color: "#718096", opacity: 0.4, width: 1 },
        move: { enable: true, speed: 2, direction: "none", random: false, straight: false, out_mode: "out" }
      },
      interactivity: {
        detect_on: "canvas",
        events: { onhover: { enable: false, mode: "repulse" }, onclick: { enable: false, mode: "push" } },
        modes: { repulse: { distance: 100 }, push: { particles_nb: 4 } }
      },
      retina_detect: true
    });

    // ---- State ----
    // photos: Array of { id, originalFile, croppedFile, previewUrl, copies }
    let photos = [];
    let nextId = 0;
    let selectedBgColor = '#FFFFFF'; // Default background color

    // Cropper modal state
    let activeCropper = null;
    let pendingCropId = null;

    // DOM refs
    const dropZone = document.getElementById('dropZone');
    const imageInput = document.getElementById('imageInput');
    const photoList = document.getElementById('photoList');
    const addMoreWrapper = document.getElementById('addMoreWrapper');
    const addMoreBtn = document.getElementById('addMoreBtn');
    const generateBtn = document.getElementById('generateBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const pdfPreview = document.getElementById('pdfPreview');
    const loading = document.getElementById('loading');
    const toggleAdvanced = document.getElementById('toggleAdvanced');
    const advancedOptions = document.getElementById('advancedOptions');
    const cropperModal = document.getElementById('cropperModal');
    const cropModalImage = document.getElementById('cropModalImage');
    const confirmCropBtn = document.getElementById('confirmCropBtn');
    const cancelCropBtn = document.getElementById('cancelCropBtn');
    const notification = document.getElementById('notification');
    const notifMsg = document.getElementById('notification-message');
    const feedbackBtn = document.getElementById('feedbackBtn');
    const feedbackModal = document.getElementById('feedbackModal');
    const closeModal = document.getElementById('closeModal');
    const feedbackForm = document.getElementById('feedbackForm');

    // ---- Notifications ----
    function showNotification(msg, isError = true) {
      notifMsg.textContent = msg;
      notification.classList.remove('bg-red-500', 'bg-green-500');
      notification.classList.add(isError ? 'bg-red-500' : 'bg-green-500');
      notification.classList.remove('translate-x-[120%]');
      notification.classList.add('translate-x-0');
      setTimeout(() => {
        notification.classList.remove('translate-x-0');
        notification.classList.add('translate-x-[120%]');
      }, 3000);
    }

    // ---- Render Photo Cards ----
    function renderPhotoList() {
      photoList.innerHTML = '';
      photos.forEach(photo => {
        const card = document.createElement('div');
        card.className = 'photo-card flex items-center gap-4 bg-gray-900/60 border border-gray-700 rounded-xl p-4';
        card.innerHTML = `
          <img src="${photo.previewUrl}" class="w-16 h-20 object-cover rounded-lg border border-gray-600 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-gray-200 truncate">${photo.originalFile.name}</p>
            <p class="text-xs text-gray-500 mt-0.5">${photo.croppedFile ? '✅ Cropped' : '⚠️ Not cropped'}</p>
          </div>
          <div class="flex flex-col items-center gap-1">
            <label class="text-xs text-gray-400">Copies</label>
            <input type="number" value="${photo.copies}" min="1" max="54"
              class="bg-gray-700 border border-gray-600 rounded-lg w-16 p-1.5 text-center text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-id="${photo.id}" />
          </div>
          <div class="flex flex-col gap-2">
            <button class="crop-btn text-xs bg-blue-500/20 hover:bg-blue-500/40 text-blue-300 border border-blue-500/30 px-3 py-1.5 rounded-lg transition-all" data-id="${photo.id}">Crop</button>
            <button class="remove-btn text-xs bg-red-500/20 hover:bg-red-500/40 text-red-400 border border-red-500/30 px-3 py-1.5 rounded-lg transition-all" data-id="${photo.id}">Remove</button>
          </div>
        `;
        photoList.appendChild(card);
      });

      // Bind copies inputs
      photoList.querySelectorAll('input[type=number]').forEach(input => {
        input.addEventListener('change', e => {
          const id = parseInt(e.target.dataset.id);
          const photo = photos.find(p => p.id === id);
          if (photo) photo.copies = Math.max(1, parseInt(e.target.value) || 1);
        });
      });

      // Bind crop buttons
      photoList.querySelectorAll('.crop-btn').forEach(btn => {
        btn.addEventListener('click', e => {
          const id = parseInt(e.target.dataset.id);
          openCropper(id);
        });
      });

      // Bind remove buttons
      photoList.querySelectorAll('.remove-btn').forEach(btn => {
        btn.addEventListener('click', e => {
          const id = parseInt(e.target.dataset.id);
          photos = photos.filter(p => p.id !== id);
          renderPhotoList();
          if (photos.length === 0) addMoreWrapper.classList.add('hidden');
        });
      });

      addMoreWrapper.classList.toggle('hidden', photos.length === 0);
    }

    // ---- Add Files ----
    function addFiles(files) {
      const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
      let added = 0;
      Array.from(files).forEach(file => {
        if (!validTypes.includes(file.type)) return;
        const photo = {
          id: nextId++,
          originalFile: file,
          croppedFile: null,
          previewUrl: URL.createObjectURL(file),
          copies: 6
        };
        photos.push(photo);
        added++;
      });
      if (added === 0) showNotification("Please upload valid image files (JPG, PNG, WEBP).");
      renderPhotoList();
    }

    // ---- Drop Zone ----
    dropZone.addEventListener('click', () => imageInput.click());
    dropZone.addEventListener('dragover', e => {
      e.preventDefault();
      dropZone.classList.add('border-blue-400', 'bg-gray-700/50');
    });
    dropZone.addEventListener('dragleave', () => {
      dropZone.classList.remove('border-blue-400', 'bg-gray-700/50');
    });
    dropZone.addEventListener('drop', e => {
      e.preventDefault();
      dropZone.classList.remove('border-blue-400', 'bg-gray-700/50');
      addFiles(e.dataTransfer.files);
    });
    imageInput.addEventListener('change', () => {
      addFiles(imageInput.files);
      imageInput.value = '';
    });
    addMoreBtn.addEventListener('click', () => imageInput.click());

    // ---- Cropper Modal ----
    function openCropper(id) {
      const photo = photos.find(p => p.id === id);
      if (!photo) return;
      pendingCropId = id;
      cropModalImage.src = photo.previewUrl;
      cropperModal.classList.remove('hidden');
      if (activeCropper) activeCropper.destroy();
      activeCropper = new Cropper(cropModalImage, {
        aspectRatio: 384 / 472,
        viewMode: 1,
        dragMode: 'move',
        autoCropArea: 1,
      });
    }

    confirmCropBtn.addEventListener('click', () => {
      if (!activeCropper || pendingCropId === null) return;
      const canvas = activeCropper.getCroppedCanvas({
        imageSmoothingEnabled: true,
        imageSmoothingQuality: 'high'
      });
      canvas.toBlob(blob => {
        const photo = photos.find(p => p.id === pendingCropId);
        if (!photo) return;
        photo.croppedFile = new File([blob], 'cropped-' + photo.originalFile.name, { type: 'image/png' });
        photo.previewUrl = URL.createObjectURL(blob);
        activeCropper.destroy();
        activeCropper = null;
        pendingCropId = null;
        cropperModal.classList.add('hidden');
        renderPhotoList();
        showNotification("Photo cropped successfully.", false);
      }, 'image/png');
    });

    cancelCropBtn.addEventListener('click', () => {
      if (activeCropper) { activeCropper.destroy(); activeCropper = null; }
      pendingCropId = null;
      cropperModal.classList.add('hidden');
    });

    // ---- Advanced Options ----
    toggleAdvanced.addEventListener('click', () => {
      const visible = advancedOptions.style.display === 'block';
      advancedOptions.style.display = visible ? 'none' : 'block';
      toggleAdvanced.textContent = visible ? 'Advanced Options' : 'Hide Advanced Options';
    });

    // ---- Background Color Picker ----
    const bgColorLabel = document.getElementById('bgColorLabel');
    const customColorBtn = document.getElementById('customColorBtn');
    const customColorInput = document.getElementById('customColorInput');
    const colorSwatches = document.querySelectorAll('.color-swatch');

    // Select a predefined swatch
    colorSwatches.forEach(swatch => {
      swatch.addEventListener('click', () => {
        colorSwatches.forEach(s => s.classList.remove('selected'));
        customColorBtn.classList.remove('selected');
        swatch.classList.add('selected');
        selectedBgColor = swatch.dataset.color;
        bgColorLabel.textContent = selectedBgColor;
      });
    });

    // Custom color picker
    customColorInput.addEventListener('input', (e) => {
      selectedBgColor = e.target.value.toUpperCase();
      bgColorLabel.textContent = selectedBgColor;
      colorSwatches.forEach(s => s.classList.remove('selected'));
      customColorBtn.classList.add('selected');
    });

    // ---- Generate PDF ----
    generateBtn.addEventListener('click', () => {
      if (photos.length === 0) {
        showNotification("Please upload at least one photo.");
        return;
      }

      const formData = new FormData();
      photos.forEach((photo, i) => {
        // Use cropped file if available, else original
        formData.append(`image_${i}`, photo.croppedFile || photo.originalFile);
        formData.append(`copies_${i}`, photo.copies);
      });
      formData.append('width', document.getElementById('width').value);
      formData.append('height', document.getElementById('height').value);
      formData.append('spacing', document.getElementById('spacing').value);
      formData.append('border', document.getElementById('border').value);
      formData.append('bg_color', selectedBgColor); // Send selected background color

      loading.classList.remove('hidden');
      generateBtn.disabled = true;
      downloadBtn.classList.add('hidden');
      pdfPreview.classList.add('hidden');

      fetch('/process', { method: 'POST', body: formData })
        .then(async response => {
          if (!response.ok) {
            let errorMsg = "Internal Error, try again later.";
            try {
              const errData = await response.json();
              if (errData.error) errorMsg = errData.error;
            } catch (e) { }

            if (response.status === 429 && errorMsg === "quota_exceeded") errorMsg = "Server Daily Quota Exceeded. Please try again later.";
            if (response.status === 410 && errorMsg === "face_detection_failed") errorMsg = "Cannot Detect Face/Background in one of the images.";

            showNotification(errorMsg);
            return null;
          }
          return response.blob();
        })
        .then(blob => {
          if (!blob) return;
          const url = URL.createObjectURL(blob);
          pdfPreview.classList.remove('hidden');
          pdfPreview.src = url;
          downloadBtn.classList.remove('hidden');
          downloadBtn.onclick = () => {
            const link = document.createElement('a');
            link.href = url;
            link.download = 'passport-sheet.pdf';
            link.click();
          };
          showNotification("PDF generated successfully!", false);
        })
        .catch(err => {
          console.error(err);
          showNotification("Image processing failed. Try again later.");
        })
        .finally(() => {
          loading.classList.add('hidden');
          generateBtn.disabled = false;
        });
    });

    // ---- Feedback ----
    feedbackBtn.addEventListener('click', () => feedbackModal.classList.remove('hidden'));
    closeModal.addEventListener('click', () => feedbackModal.classList.add('hidden'));
    feedbackForm.addEventListener('submit', e => {
      e.preventDefault();
      const contact = feedbackForm.contact.value.trim();
      const message = feedbackForm.message.value.trim();
      if (!contact || !message) { showNotification("Please fill out all fields."); return; }
      const btn = feedbackForm.querySelector('button[type="submit"]');
      btn.disabled = true; btn.textContent = 'Submitting...';
      emailjs.send("service_5a1u7at", "template_5zf7ngf", {
        contact, message,
        user_agent: navigator.userAgent,
        time: new Date().toLocaleString()
      }).then(() => {
        showNotification("Feedback submitted. Thank you!", false);
        feedbackModal.classList.add('hidden');
        feedbackForm.reset();
      }).catch(err => {
        console.error(err);
        showNotification("Failed to send feedback. Please try again.");
      }).finally(() => {
        btn.disabled = false; btn.textContent = 'Submit';
      });
    });
  
