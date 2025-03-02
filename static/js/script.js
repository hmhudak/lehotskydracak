document.addEventListener("DOMContentLoaded", function() {

    // =========================================================
    // 1) MARKDOWN TEXTAREA + PREVIEW
    // =========================================================

    const textarea = document.getElementById('markdown-input');
    const preview = document.getElementById('markdown-preview');

    function autoResizeTextarea() {
        if (!textarea) return;
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
    }

    function transformLocalImages(container) {
        if (!container) return;
        const imgs = container.querySelectorAll('img');
        imgs.forEach(img => {
            let altText = img.alt || '';
            let parts = altText.split('|').map(p => p.trim());
            let baseAlt = parts[0] || 'Obrázok';
            let scale = 100;
            let caption = '-';
            let align = 'center';

            for (let i = 1; i < parts.length; i++) {
                const p = parts[i];
                if (p.startsWith('scale=')) {
                    let val = parseInt(p.replace('scale=', '').trim(), 10);
                    if (val < 10) val = 10;
                    if (val > 100) val = 100;
                    scale = val;
                } else if (p.startsWith('caption=')) {
                    caption = p.replace('caption=', '').trim();
                } else if (p.startsWith('align=')) {
                    align = p.replace('align=', '').trim().toLowerCase();
                }
            }
            img.alt = baseAlt;

            let figure = document.createElement('figure');
            let figureStyle = 'background:#f1f1f1; padding:5px; border:1px solid #ccc; clear:both;';
            if (align === 'left') {
                figureStyle += `float:left; margin:0 10px 10px 0; width:${scale}%;`;
            } else if (align === 'right') {
                figureStyle += `float:right; margin:0 0 10px 10px; width:${scale}%;`;
            } else {
                figureStyle += `margin:0 auto; width:${scale}%; display:block;`;
            }
            figure.setAttribute('style', figureStyle);

            img.style.display = 'block';
            img.style.height = 'auto';
            img.style.width = '100%';

            let parent = img.parentNode;
            parent.replaceChild(figure, img);
            figure.appendChild(img);

            if (caption && caption !== '-') {
                let figcap = document.createElement('figcaption');
                figcap.textContent = caption;
                figcap.style.textAlign = 'center';
                figcap.style.color = '#555';
                figcap.style.fontSize = 'smaller';
                figure.appendChild(figcap);
            }
        });
    }

    function updatePreview() {
        if (!preview || !textarea) return;
        preview.innerHTML = marked.parse(textarea.value);
        transformLocalImages(preview);
    }

    if (textarea) {
        textarea.style.minHeight = '200px';
        textarea.addEventListener('input', function() {
            updatePreview();
            autoResizeTextarea();
        });
        updatePreview();
        autoResizeTextarea();
    }

    // =========================================================
    // 2) MARKDOWN TOOLBAR ACTIONS 
    // =========================================================
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
                    textarea.focus();
                    textarea.selectionStart = start + before.length;
                    textarea.selectionEnd = textarea.selectionStart + selected.length;
                    updatePreview();
                    autoResizeTextarea();
                }

                function restoreFocusAndSelection(replaced, startPos) {
                    textarea.focus();
                    textarea.selectionStart = startPos + replaced.length;
                    textarea.selectionEnd = textarea.selectionStart;
                    updatePreview();
                    autoResizeTextarea();
                }

                if (action === 'heading' && level) {
                    let hashes = '#'.repeat(parseInt(level)) + ' ';
                    wrapText(hashes);
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
                    const selected = text.substring(start, end);
                    const before = '[';
                    const after = '](http://)';
                    const newText = text.substring(0, start) + before + selected + after + text.substring(end);
                    textarea.value = newText;
                    textarea.focus();
                    let sLen = selected.length;
                    let cursorPos = start + before.length + sLen + 3;
                    textarea.selectionStart = cursorPos;
                    textarea.selectionEnd = cursorPos + 4; 
                    updatePreview();
                    autoResizeTextarea();
                } else if (action === 'image') {
                    let imageModalElement = document.getElementById('imageModal');
                    if (imageModalElement) {
                        let imageModal = new bootstrap.Modal(imageModalElement);
                        showImageModal();
                        imageModal.show();
                    }
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

    // =========================================================
    // 3) MODAL PRE OBRÁZKY (Galéria + Upload/URL)
    // =========================================================

    const scaleRange = document.getElementById('image-scale');
    const scaleValue = document.getElementById('image-scale-value');
    const insertBtn = document.getElementById('insert-image-btn');
    const altInput = document.getElementById('image-alt');
    const alignSelect = document.getElementById('image-align');
    const captionInput = document.getElementById('image-caption');

    if (scaleRange && scaleValue) {
        scaleRange.addEventListener('input', function() {
            scaleValue.textContent = scaleRange.value + '%';
        });
    }

    let galleryLoaded = false;
    function showImageModal() {
        if (galleryLoaded) return;
        fetch('/api/list_images')
          .then(r => r.json())
          .then(data => {
              const galleryContainer = document.getElementById('gallery-container');
              if (!galleryContainer) return;
              galleryContainer.innerHTML = '';

              data.images.forEach(img => {
                  let thumb = document.createElement('img');
                  thumb.src = img.url;
                  thumb.style.maxWidth = '100px';
                  thumb.style.maxHeight = '100px';
                  thumb.style.cursor = 'pointer';
                  thumb.classList.add('m-1');

                  thumb.addEventListener('click', () => {
                      const urlInput = document.getElementById('image-url');
                      if (urlInput) {
                          urlInput.value = img.url;
                      }
                      let allThumbs = galleryContainer.querySelectorAll('img');
                      allThumbs.forEach(t => { t.style.border = 'none'; });
                      thumb.style.border = '3px solid blue';
                  });

                  galleryContainer.appendChild(thumb);
              });
              galleryLoaded = true;
          })
          .catch(err => console.error("Chyba pri načítaní galérie:", err));
    }

    if (insertBtn) {
        insertBtn.addEventListener('click', function() {
            if (!textarea) return;

            const urlInput = document.getElementById('image-url');
            const fileInput = document.getElementById('image-file');

            let text = textarea.value;
            let start = textarea.selectionStart;
            let end = textarea.selectionEnd;

            function insertImage(mdUrl) {
                let altText = altInput.value.trim() || "Obrázok";
                let scale = parseInt(scaleRange.value, 10) || 100;
                let caption = captionInput.value.trim() || "-";
                let align = alignSelect.value || "center";

                let altWithAttrs = `${altText} | scale=${scale} | caption=${caption} | align=${align}`;

                const toInsert = `![${altWithAttrs}](${mdUrl})`;
                const newText = text.substring(0, start) + toInsert + text.substring(end);
                textarea.value = newText;
                textarea.focus();
                textarea.selectionStart = start + toInsert.length;
                textarea.selectionEnd = textarea.selectionStart;
                updatePreview();
                autoResizeTextarea();
            }

            let imageModalElement = document.getElementById('imageModal');
            let imageModal = bootstrap.Modal.getInstance(imageModalElement);
            if (!imageModal) {
                imageModal = new bootstrap.Modal(imageModalElement);
            }

            if (fileInput && fileInput.files && fileInput.files.length > 0) {
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
                        let allThumbs = document.querySelectorAll('#gallery-container img');
                        allThumbs.forEach(t => { t.style.border = 'none'; });
                        if (urlInput) urlInput.value = '';
                        fileInput.value = '';
                        captionInput.value = '';
                        altInput.value = '';
                        scaleRange.value = '100';
                        scaleValue.textContent = '100%';
                        alignSelect.value = 'center';
                    } else {
                        // tu môžeš otvoriť modálne okno s chybou, 
                        // alebo pridať nejakú hlášku do .modal-body
                        console.error("Chyba pri nahrávaní:", data.error);
                    }
                })
                .catch(err => {
                    console.error("Chyba pri nahrávaní:", err);
                });
            } else {
                let urlVal = urlInput.value.trim();
                if (urlVal) {
                    insertImage(urlVal);
                }
                imageModal.hide();
                let allThumbs = document.querySelectorAll('#gallery-container img');
                allThumbs.forEach(t => { t.style.border = 'none'; });
                urlInput.value = '';
                if (fileInput) fileInput.value = '';
                captionInput.value = '';
                altInput.value = '';
                scaleRange.value = '100';
                scaleValue.textContent = '100%';
                alignSelect.value = 'center';
            }
        });
    }

    // =========================================================
    // 4) FULLSCREEN VIEW PO KLIKNUTÍ NA OBRÁZOK (page_view)
    // =========================================================
    const pageContent = document.querySelector('.page-content');
    const imageFullModal = document.getElementById('imageFullModal');
    const imageFullView = document.getElementById('image-full-view');
    if (pageContent && imageFullModal && imageFullView) {
        pageContent.addEventListener('click', function(e) {
            if (e.target.tagName.toLowerCase() === 'img') {
                const fullsrc = e.target.getAttribute('data-fullsrc');
                if (fullsrc) {
                    imageFullView.setAttribute('src', fullsrc);
                    imageFullView.style.maxWidth = '100%';
                    imageFullView.style.maxHeight = '90vh';
                    imageFullView.style.objectFit = 'contain';
                    let modal = new bootstrap.Modal(imageFullModal);
                    modal.show();
                }
            }
        });
    }

    // =========================================================
    // 6) PRIDANIE NOVÉHO ŠTÍTKU (AJAX)
    // =========================================================
    const newTagButton = document.getElementById('new-tag-button');
    if (newTagButton) {
        newTagButton.addEventListener('click', function() {
            const nameInput = document.getElementById('new-tag-name');
            const colorInput = document.getElementById('new-tag-color');
            if (!nameInput || !colorInput) return;

            const tagName = nameInput.value.trim();
            const tagColor = colorInput.value.trim();
            if (!tagName || !tagColor) {
                // opäť, mohol by si zobraziť vlastné modálne okno "chyba"
                console.error("Zadajte názov a farbu štítku.");
                return;
            }

            const formData = new FormData();
            formData.append('name', tagName);
            formData.append('color', tagColor);

            fetch('/create_tag', {
                method: 'POST',
                body: formData
            })
            .then(resp => resp.json())
            .then(data => {
                if (data.error) {
                    console.error(data.error);
                } else {
                    const tagList = document.getElementById('tag-list');
                    if (tagList) {
                        const wrapper = document.createElement('div');
                        wrapper.classList.add('form-check', 'd-flex', 'align-items-center', 'mb-1');
                        wrapper.setAttribute('data-tag-id', data.tag_id);
                        wrapper.innerHTML = `
                            <input class="form-check-input" type="checkbox" name="tag_ids"
                                   value="${data.tag_id}" id="tag-${data.tag_id}" checked>
                            <label class="form-check-label ms-1" for="tag-${data.tag_id}">
                                <span style="background:${data.color}; color:#fff; padding:2px 4px; border-radius:4px;">
                                    ${data.name}
                                </span>
                            </label>
                        `;
                        tagList.appendChild(wrapper);
                    }
                    nameInput.value = '';
                    colorInput.value = '#dd4477';
                }
            })
            .catch(err => {
                console.error("Chyba pri vytváraní štítku:", err);
            });
        });
    }

    // =========================================================
    // TOGGLE NOVÉHO ŠTÍTKU (zobrazenie/skrytie panelu)
    // =========================================================
    const toggleNewTagFormButton = document.getElementById('toggle-new-tag-form');
    const newTagPanel = document.getElementById('new-tag-panel');
    if (toggleNewTagFormButton && newTagPanel) {
        toggleNewTagFormButton.addEventListener('click', function() {
            if (newTagPanel.style.display === 'none' || !newTagPanel.style.display) {
                newTagPanel.style.display = 'block';
            } else {
                newTagPanel.style.display = 'none';
            }
        });
    }


    // =========================================================
    // 7) MAZANIE ŠTÍTKOV – cez samostatný modal
    // =========================================================
    const deleteTagBtn = document.getElementById('delete-tag-btn');
    const deleteTagsModal = document.getElementById('deleteTagsModal'); 
    const deleteTagsList = document.getElementById('delete-tags-list');
    const confirmDeleteTagsBtn = document.getElementById('confirm-delete-tags-btn');
    if (deleteTagBtn && deleteTagsModal && deleteTagsList && confirmDeleteTagsBtn) {

        // Otvoríme modal, v ňom zobrazíme zoznam všetkých existujúcich štítkov (okrem 'stránka')
        deleteTagBtn.addEventListener('click', function() {
            // vyčistíme
            deleteTagsList.innerHTML = '';
            // Natiahneme /api/tags
            fetch('/api/tags')
            .then(r => r.json())
            .then(tags => {
                tags.forEach(t => {
                    let div = document.createElement('div');
                    div.classList.add('form-check', 'mb-1');
                    div.innerHTML = `
                      <input class="form-check-input" type="checkbox" value="${t.tag_id}" id="del-tag-${t.tag_id}">
                      <label class="form-check-label ms-1" for="del-tag-${t.tag_id}">
                        <span style="background:${t.color}; color:#fff; padding:2px 4px; border-radius:4px;">
                          ${t.name}
                        </span>
                      </label>
                    `;
                    deleteTagsList.appendChild(div);
                });
                let modal = new bootstrap.Modal(deleteTagsModal);
                modal.show();
            })
            .catch(err => {
                console.error("Chyba pri načítavaní štítkov:", err);
            });
        });

        // Po stlačení "Zmazať vybrané" -> zmažeme ich
        confirmDeleteTagsBtn.addEventListener('click', function() {
            // zistíme, ktoré checknuté
            const checked = deleteTagsList.querySelectorAll('input[type="checkbox"]:checked');
            if (!checked.length) {
                // Nevybral žiadne => len zatvoríme
                let modal = bootstrap.Modal.getInstance(deleteTagsModal);
                if (modal) modal.hide();
                return;
            }
            let tagIds = [];
            checked.forEach(ch => {
                tagIds.push(ch.value);
            });
            // Pošleme POST na /delete_tags
            const formData = new FormData();
            tagIds.forEach(id => formData.append('tag_ids[]', id));
            fetch('/delete_tags', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    console.error("Chyba pri mazaní štítkov:", data.error);
                } else {
                    // success => zmažeme tie checknuté z pravého panelu
                    let mainTagList = document.getElementById('tag-list');
                    if (mainTagList) {
                        tagIds.forEach(tid => {
                            let el = mainTagList.querySelector(`[data-tag-id="${tid}"]`);
                            if (el) el.remove();
                        });
                    }
                }
                let modal = bootstrap.Modal.getInstance(deleteTagsModal);
                if (modal) modal.hide();
            })
            .catch(err => {
                console.error("Chyba pri mazaní štítkov:", err);
            });
        });
    }

    // =========================================================
    // 8) MAZANIE STRÁNKY – modálne okno, nie alert
    // =========================================================
    const pageDeleteForms = document.querySelectorAll('form[action="/delete_page"]');
    // predpokladáme, že form obsahuje input name="page_id"
    if (pageDeleteForms.length > 0) {
        // nahradíme submit event modálnym oknom
        pageDeleteForms.forEach(frm => {
            frm.addEventListener('submit', function(e) {
                e.preventDefault(); // zrušíme
                let pageIdInput = frm.querySelector('input[name="page_id"]');
                if (!pageIdInput) return;

                let modalDelPage = document.getElementById('deletePageModal');
                if (!modalDelPage) return;
                // ukážeme modal
                let mdp = new bootstrap.Modal(modalDelPage);
                mdp.show();

                // Keď user potvrdí "Zmazať", spravíme fetch POST
                const confirmPageDeleteBtn = document.getElementById('confirm-page-delete-btn');
                if (confirmPageDeleteBtn) {
                    confirmPageDeleteBtn.onclick = () => {
                        let pidVal = pageIdInput.value;
                        const fd = new FormData();
                        fd.append('page_id', pidVal);
                        fetch('/delete_page', {
                            method: 'POST',
                            body: fd
                        })
                        .then(r => r.json())
                        .then(resp => {
                            if (resp.success) {
                                mdp.hide();
                                // presmerujeme na index
                                window.location.href = '/';
                            } else {
                                console.error("Chyba pri mazaní stránky:", resp.error);
                            }
                        })
                        .catch(err => {
                            console.error("Chyba pri fetch:", err);
                        });
                    };
                }
            });
        });
    }

    // =========================================================
    // 9) HLAVNÁ STRÁNKA: FILTROVANIE OR/AND
    // =========================================================
    const tagFilterContainer = document.getElementById('tag-filter');
    const filterModeToggle = document.getElementById('filter-mode-toggle');
    const pageListContainer = document.getElementById('page-list');

    if (tagFilterContainer && filterModeToggle && pageListContainer) {
        let allTags = [];
        let allPages = [];

        Promise.all([
            fetch('/api/tags').then(r => r.json()),
            fetch('/api/pages').then(r => r.json())
        ]).then(([tags, pages]) => {
            allTags = tags;
            allPages = pages;
            renderTagFilter(allTags);
            renderPageList(allPages, []);
        }).catch(err => {
            console.error("Chyba pri načítaní tags/pages:", err);
        });

        function renderTagFilter(tags) {
            tagFilterContainer.innerHTML = '';
            tags.forEach(t => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.classList.add('btn', 'btn-sm', 'm-1', 'tag-filter-btn');
                btn.style.border = `1px solid ${t.color}`;
                btn.style.color = t.color;
                btn.textContent = t.name;
                btn.dataset.tagId = t.tag_id;
                btn.dataset.active = '0';
                btn.addEventListener('click', onTagClick);
                tagFilterContainer.appendChild(btn);
            });
        }

        function onTagClick(e) {
            const btn = e.target;
            const isActive = (btn.dataset.active === '1');
            btn.dataset.active = isActive ? '0' : '1';
            if (!isActive) {
                btn.style.backgroundColor = btn.style.color;
                btn.style.color = '#fff';
            } else {
                btn.style.color = btn.style.borderColor;
                btn.style.backgroundColor = 'transparent';
            }
            refreshFilter();
        }

        filterModeToggle.addEventListener('change', function() {
            refreshFilter();
        });

        function refreshFilter() {
            const activeTagIds = [];
            document.querySelectorAll('.tag-filter-btn').forEach(b => {
                if (b.dataset.active === '1') {
                    activeTagIds.push(parseInt(b.dataset.tagId, 10));
                }
            });
            renderPageList(allPages, activeTagIds);
        }

        function renderPageList(pages, activeTagIds) {
            pageListContainer.innerHTML = '';
            const isAndMode = filterModeToggle.checked;
            if (activeTagIds.length === 0) {
                pages.forEach(p => {
                    pageListContainer.appendChild(createPageRow(p));
                });
                return;
            }
            pages.forEach(p => {
                const pTagIds = p.tags.map(t => t.tag_id);
                if (isAndMode) {
                    const hasAll = activeTagIds.every(tid => pTagIds.includes(tid));
                    if (hasAll) {
                        pageListContainer.appendChild(createPageRow(p));
                    }
                } else {
                    const hasAny = activeTagIds.some(tid => pTagIds.includes(tid));
                    if (hasAny) {
                        pageListContainer.appendChild(createPageRow(p));
                    }
                }
            });
        }

        function createPageRow(page) {
            const div = document.createElement('div');
            div.classList.add('mb-2');

            const a = document.createElement('a');
            // tu už ideme slug, nie page_id
            a.href = `/page/${page.slug}`;
            a.textContent = page.title;
            a.classList.add('me-2');
            div.appendChild(a);

            page.tags.forEach(t => {
                const span = document.createElement('span');
                span.textContent = t.name;
                span.style.backgroundColor = t.color;
                span.style.color = '#fff';
                span.style.padding = '2px 4px';
                span.style.borderRadius = '4px';
                span.classList.add('me-1');
                div.appendChild(span);
            });
            return div;
        }
    }

});
