document.addEventListener("DOMContentLoaded", function() {
    const textarea = document.getElementById('markdown-input');
    const preview = document.getElementById('markdown-preview');

    function updatePreview() {
        if (preview && textarea) {
            preview.innerHTML = marked.parse(textarea.value);
        }
    }

    if (textarea) {
        textarea.addEventListener('input', updatePreview);
        updatePreview(); // initial
    }

    function restoreFocusAndSelection(replaced, start) {
        if (textarea) {
            textarea.focus();
            textarea.selectionStart = start + replaced.length;
            textarea.selectionEnd = textarea.selectionStart;
            updatePreview();
        }
    }

    if (textarea) {
        document.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', function() {
                if (!textarea) return;
                const action = this.getAttribute('data-action');
                const level = this.getAttribute('data-level');
                let start = textarea.selectionStart;
                let end = textarea.selectionEnd;
                let text = textarea.value;

                function wrapText(before, after='') {
                    const selected = text.substring(start, end);
                    const newText = text.substring(0, start) + before + selected + after + text.substring(end);
                    textarea.value = newText;
                    // po wrapText necháme fokus a selection na vložený text
                    textarea.focus();
                    textarea.selectionStart = start + before.length;
                    textarea.selectionEnd = textarea.selectionStart + selected.length;
                    updatePreview();
                }

                if (action === 'heading' && level) {
                    let hashes = '#'.repeat(parseInt(level)) + ' ';
                    wrapText(hashes, '');
                } else if (action === 'bold') {
                    wrapText('**','**');
                } else if (action === 'italic') {
                    wrapText('*','*');
                } else if (action === 'hr') {
                    const insert = '\n---\n';
                    const newText = text.substring(0, start) + insert + text.substring(end);
                    textarea.value = newText;
                    restoreFocusAndSelection(insert, start);
                } else if (action === 'link') {
                    // link: vložíme [selected](http://)
                    // potom kurzor umiestnime do http://
                    const selected = text.substring(start, end);
                    const before = '[';
                    const after = '](http://)';
                    const newText = text.substring(0, start) + before + selected + after + text.substring(end);
                    textarea.value = newText;
                    textarea.focus();
                    // Teraz vyberieme http:// v linku.
                    // Pozícia http:// začína za selected textom: 
                    // [selected](http://)
                    // Po vložení:
                    // start+before.length+selected.length+2 sú znaky pre '](, začiatok http
                    let sLen = selected.length;
                    let cursorPos = start + before.length + sLen + 3; // '(' je o 2 znaky po selected, http začína o 3
                    textarea.selectionStart = cursorPos;
                    textarea.selectionEnd = cursorPos + 4; // vyberieme "http"
                    updatePreview();
                } else if (action === 'image') {
                    let imageModal = new bootstrap.Modal(document.getElementById('imageModal'));
                    imageModal.show();
                } else if (action === 'ul') {
                    const selected = text.substring(start, end);
                    const lines = selected.split('\n').map(l => '- ' + l);
                    const replaced = lines.join('\n');
                    textarea.value = text.substring(0, start) + replaced + text.substring(end);
                    restoreFocusAndSelection(replaced, start);
                } else if (action === 'ol') {
                    const selected = text.substring(start, end);
                    const lines = selected.split('\n').map((l,i) => (i+1) + '. ' + l);
                    const replaced = lines.join('\n');
                    textarea.value = text.substring(0, start) + replaced + text.substring(end);
                    restoreFocusAndSelection(replaced, start);
                }
            });
        });
    }

    const insertBtn = document.getElementById('insert-image-btn');
    const scaleRange = document.getElementById('image-scale');
    const scaleValue = document.getElementById('image-scale-value');
    const alignSelect = document.getElementById('image-align');

    if (scaleRange) {
        scaleRange.addEventListener('input', function() {
            scaleValue.textContent = scaleRange.value + '%';
        });
    }

    if (insertBtn) {
        insertBtn.addEventListener('click', function() {
            const urlInput = document.getElementById('image-url');
            const fileInput = document.getElementById('image-file');
            const captionInput = document.getElementById('image-caption');
            const scaleInput = document.getElementById('image-scale');
            const alignInput = document.getElementById('image-align');
            const altText = "Obrázok"; 
            const url = urlInput.value.trim();
            const caption = captionInput.value.trim();
            const scale = parseInt(scaleInput.value,10);
            const align = alignInput.value; // 'left','right','center'

            if (!textarea) return;

            let start = textarea.selectionStart;
            let end = textarea.selectionEnd;
            let text = textarea.value;

            function insertImage(mdUrl) {
                let altWithAttrs = altText;
                if (scale !== 100) {
                    altWithAttrs += ` | scale=${scale}`;
                }
                if (caption !== '') {
                    altWithAttrs += ` | caption=${caption}`;
                }
                if (align && align !== 'center') {
                    altWithAttrs += ` | align=${align}`;
                } else {
                    // align center je default
                    altWithAttrs += ` | align=center`;
                }

                const toInsert = `![${altWithAttrs}](${mdUrl})`;
                const newText = text.substring(0, start) + toInsert + text.substring(end);
                textarea.value = newText;
                textarea.focus();
                textarea.selectionStart = start + toInsert.length;
                textarea.selectionEnd = textarea.selectionStart;
                updatePreview();
            }

            let imageModal = bootstrap.Modal.getInstance(document.getElementById('imageModal'));

            if (fileInput.files && fileInput.files.length > 0) {
                const formData = new FormData();
                formData.append('image', fileInput.files[0]);
                fetch('/upload_image', {
                    method: 'POST',
                    body: formData
                })
                .then(r => r.json())
                .then(data => {
                    if (data.url) {
                        insertImage(data.url);
                        imageModal.hide();
                        urlInput.value = '';
                        captionInput.value = '';
                        fileInput.value = '';
                        scaleInput.value = '100';
                        scaleValue.textContent = '100%';
                        alignInput.value = 'center';
                    } else {
                        alert("Chyba pri nahrávaní obrázka: " + (data.error || 'Neznáma chyba'));
                    }
                })
                .catch(err => {
                    alert("Chyba: " + err);
                });
            } else {
                if (url) {
                    insertImage(url);
                }
                imageModal.hide();
                urlInput.value = '';
                captionInput.value = '';
                fileInput.value = '';
                scaleInput.value = '100';
                scaleValue.textContent = '100%';
                alignInput.value = 'center';
            }
        });
    }

    const pageContent = document.querySelector('.page-content');
    const imageFullModal = document.getElementById('imageFullModal');
    const imageFullView = document.getElementById('image-full-view');
    if (pageContent && imageFullView && imageFullModal) {
        pageContent.addEventListener('click', function(e) {
            if (e.target.tagName.toLowerCase() === 'img') {
                const fullsrc = e.target.getAttribute('data-fullsrc');
                if (fullsrc) {
                    imageFullView.setAttribute('src', fullsrc);
                    let modal = new bootstrap.Modal(imageFullModal);
                    modal.show();
                }
            }
        });
    }

    // Pre images.html - mazanie obrázku
    const deleteBtns = document.querySelectorAll('.delete-image-btn');
    const deleteConfirmModal = document.getElementById('deleteConfirmModal');
    const deleteFilenameSpan = document.getElementById('delete-filename');
    const deleteFilenameInput = document.getElementById('delete-filename-input');

    if (deleteBtns && deleteConfirmModal && deleteFilenameSpan && deleteFilenameInput) {
        deleteBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const filename = this.getAttribute('data-filename');
                deleteFilenameSpan.textContent = filename;
                deleteFilenameInput.value = filename;
                let modal3 = new bootstrap.Modal(deleteConfirmModal);
                modal3.show();
            });
        });
    }

});
