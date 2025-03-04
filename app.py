import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
import markdown as md
from bs4 import BeautifulSoup
import cloudinary
import cloudinary.uploader
import cloudinary.api
import unicodedata
import re

# AUTHLIB
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'verysecretkey')

# Google OAuth nastavenie - Discovery + nastavený api_base_url
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',

    # Tu pridávame base URL pre google.get('userinfo')
    api_base_url='https://www.googleapis.com/oauth2/v2/',

    authorize_params={
        'prompt': 'consent',
        'access_type': 'offline'
    },
    client_kwargs={
        'scope': 'openid email profile'
    }
)

DATABASE_URL = os.environ.get('DATABASE_URL')
CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL')
cloudinary.config(cloudinary_url=CLOUDINARY_URL)

def get_db():
    if not hasattr(g, 'db_conn'):
        g.db_conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return g.db_conn

@app.teardown_appcontext
def close_connection(exception):
    if hasattr(g, 'db_conn'):
        g.db_conn.close()

def init_db():
    """
    Inicializácia DB. Vytvorí tabuľky, ak neexistujú.
    Nezabudni si vytvoriť aj CREATE TABLE users, ak to neriešiš samostatne.
    """
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id SERIAL PRIMARY KEY,
            title TEXT UNIQUE NOT NULL,
            content TEXT,
            visible_to TEXT NOT NULL DEFAULT 'All',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            slug TEXT
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            color TEXT NOT NULL
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS page_tags (
            page_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY(page_id, tag_id),
            FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );
    """)

    # Tu môže byť aj CREATE TABLE users

    conn.commit()

with app.app_context():
    init_db()

def is_logged_in():
    return 'user' in session

def is_admin():
    return is_logged_in() and session['user']['role'] == 'Admin'

def remove_diacritics(text):
    nfkd_form = unicodedata.normalize('NFKD', text)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('ASCII')
    return only_ascii

def generate_slug(title, c, existing_id=None):
    base = remove_diacritics(title)
    base = re.sub(r'[^a-zA-Z0-9\s]+', '', base)
    base = re.sub(r'\s+', ' ', base).strip()
    base = base.replace(' ', '+')
    slug = base.lower() if base else 'stranka'

    candidate = slug
    i = 2
    while True:
        if existing_id:
            c.execute("SELECT id FROM pages WHERE slug=%s AND id<>%s", (candidate, existing_id))
        else:
            c.execute("SELECT id FROM pages WHERE slug=%s", (candidate,))
        row = c.fetchone()
        if not row:
            return candidate
        candidate = slug + f"-{i}"
        i += 1

def process_images(html):
    soup = BeautifulSoup(html, 'html.parser')
    imgs = soup.find_all('img')
    for img in imgs:
        alt = img.get('alt', '')
        parts = [p.strip() for p in alt.split('|')]
        base_alt = parts[0] if parts else 'Obrázok'
        scale = 100
        caption = '-'
        align = 'center'
        for p in parts[1:]:
            if p.startswith('scale='):
                try:
                    val = int(p.replace('scale=', '').strip())
                    if val < 10: val = 10
                    if val > 100: val = 100
                    scale = val
                except:
                    pass
            elif p.startswith('caption='):
                caption = p.replace('caption=', '').strip()
            elif p.startswith('align='):
                align = p.replace('align=', '').strip().lower()

        img['alt'] = base_alt
        if not img.get('data-fullsrc'):
            img['data-fullsrc'] = img.get('src', '')

        figure = soup.new_tag('figure')
        figure_style = 'background:#f1f1f1; padding:5px; border:1px solid #ccc; clear:both;'
        if align == 'left':
            figure_style += f'float:left; margin:0 10px 10px 0; width:{scale}%;'
        elif align == 'right':
            figure_style += f'float:right; margin:0 0 10px 10px; width:{scale}%;'
        else:
            figure_style += f'margin:0 auto; width:{scale}%; display:block;'
        figure['style'] = figure_style

        img_style = 'width:100%; display:block; height:auto;'
        img['style'] = img_style

        img.replace_with(figure)
        figure.append(img)

        if caption and caption != '-':
            figcap = soup.new_tag('figcaption')
            figcap.string = caption
            figcap['style'] = 'text-align:center; color:#555; font-size:smaller;'
            figure.append(figcap)

    return str(soup)

# -------- Google OAuth routes --------

@app.route('/auth')
def auth():
    if is_logged_in():
        return redirect(url_for('index'))
    redirect_uri = url_for('auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    token = google.authorize_access_token()
    # Namiesto 'userinfo' tu funguje vďaka api_base_url:
    resp = google.get('userinfo')
    profile = resp.json()

    email = profile.get('email')
    first_name = profile.get('given_name', '')
    last_name = profile.get('family_name', '')

    if not email:
        return "Nepodarilo sa získať email z Google profilu.", 400

    user_data = load_or_create_user(email, first_name, last_name)

    session['user'] = {
        'id': user_data['id'],
        'email': user_data['email'],
        'role': user_data['role'],
        'first_name': user_data['first_name'],
        'last_name': user_data['last_name']
    }

    return redirect(url_for('index'))

def load_or_create_user(email, first_name, last_name):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count_all = c.fetchone()[0]

    c.execute("SELECT * FROM users WHERE email=%s", (email,))
    row = c.fetchone()
    if row:
        c.execute("""UPDATE users
                     SET first_name=%s, last_name=%s
                     WHERE email=%s
                     RETURNING *""",
                  (first_name, last_name, email))
        updated_row = c.fetchone()
        conn.commit()
        return updated_row
    else:
        new_role = 'Admin' if count_all == 0 else 'Player'
        c.execute("""INSERT INTO users (email, first_name, last_name, role)
                     VALUES (%s, %s, %s, %s)
                     RETURNING *""",
                  (email, first_name, last_name, new_role))
        new_row = c.fetchone()
        conn.commit()
        return new_row

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/')
def index():
    if not is_logged_in():
        return redirect(url_for('auth'))
    return render_template('index.html')

@app.route('/admin/users')
def manage_users():
    if not is_admin():
        return "Nemáte oprávnenie.", 403
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, email, first_name, last_name, role FROM users ORDER BY email")
    users = c.fetchall()
    return render_template('manage_users.html', users=users)

@app.route('/admin/update_role', methods=['POST'])
def update_role():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403

    user_id = request.form.get('user_id')
    new_role = request.form.get('role')
    if not user_id or not new_role:
        return jsonify({"error": "Chýba user_id alebo role"}), 400

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET role=%s WHERE id=%s", (new_role, user_id))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/pages')
def api_pages():
    if not is_logged_in():
        return jsonify([])
    conn = get_db()
    c = conn.cursor()
    if is_admin():
        c.execute("""
            SELECT p.id, p.title, p.slug, p.visible_to,
                   COALESCE(json_agg(json_build_object('tag_id', t.id, 'name', t.name, 'color', t.color)
                                     ORDER BY t.name) FILTER (WHERE t.name IS NOT NULL), '[]') AS tags
            FROM pages p
            LEFT JOIN page_tags pt ON p.id = pt.page_id
            LEFT JOIN tags t ON pt.tag_id = t.id AND t.name <> 'stránka'
            GROUP BY p.id
            ORDER BY p.title;
        """)
    else:
        c.execute("""
            SELECT p.id, p.title, p.slug, p.visible_to,
                   COALESCE(json_agg(json_build_object('tag_id', t.id, 'name', t.name, 'color', t.color)
                                     ORDER BY t.name) FILTER (WHERE t.name IS NOT NULL), '[]') AS tags
            FROM pages p
            LEFT JOIN page_tags pt ON p.id = pt.page_id
            LEFT JOIN tags t ON pt.tag_id = t.id AND t.name <> 'stránka'
            WHERE p.visible_to='All'
            GROUP BY p.id
            ORDER BY p.title;
        """)
    rows = c.fetchall()
    result = []
    for row in rows:
        result.append({
            'page_id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
            'visible_to': row['visible_to'],
            'tags': row['tags']
        })
    return jsonify(result)

@app.route('/api/tags')
def api_tags():
    if not is_logged_in():
        return jsonify([])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, color FROM tags WHERE name <> 'stránka' ORDER BY name;")
    rows = c.fetchall()
    result = []
    for r in rows:
        result.append({
            'tag_id': r['id'],
            'name': r['name'],
            'color': r['color']
        })
    return jsonify(result)

@app.route('/create_tag', methods=['POST'])
def create_tag():
    if not is_admin():
        return jsonify({"error":"Not allowed"}), 403
    tag_name = request.form.get('name', '').strip()
    tag_color = request.form.get('color', '').strip()
    if not tag_name or not tag_color:
        return jsonify({"error":"Chýba meno alebo farba štítku."}), 400
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO tags (name, color) VALUES (%s, %s) RETURNING id;", (tag_name, tag_color))
        new_id = c.fetchone()[0]
        conn.commit()
        return jsonify({"tag_id": new_id, "name": tag_name, "color": tag_color})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/delete_tags', methods=['POST'])
def delete_tags():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    tag_ids = request.form.getlist('tag_ids[]')
    if not tag_ids:
        return jsonify({"error":"No tag_ids provided"}), 400
    conn = get_db()
    c = conn.cursor()
    try:
        for tid in tag_ids:
            c.execute("DELETE FROM tags WHERE id=%s AND name<>'stránka'", (tid,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if not is_admin():
        return jsonify({"error":"Not allowed"}), 403
    if 'image' not in request.files:
        return jsonify({"error":"No file"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error":"No filename"}), 400

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    if not allowed_file(file.filename):
        return jsonify({"error":"File not allowed"}), 400

    try:
        result = cloudinary.uploader.upload(file, folder="lehotskydracak")
        if 'secure_url' in result:
            return jsonify({"url": result['secure_url']})
        else:
            return jsonify({"error":"Upload failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/images')
def list_images():
    if not is_admin():
        return redirect(url_for('index'))
    try:
        resources = cloudinary.api.resources(type='upload', prefix='lehotskydracak/', max_results=100)
    except Exception as e:
        print("Cloudinary list error:", e)
        resources = {'resources': []}
    images = []
    for r in resources.get('resources', []):
        images.append({'public_id': r['public_id'], 'url': r['secure_url']})
    return render_template('images.html', images=images)

@app.route('/api/list_images')
def api_list_images():
    if not is_admin():
        return jsonify({"images":[]})
    try:
        resources = cloudinary.api.resources(type='upload', prefix='lehotskydracak/', max_results=100)
        images = []
        for r in resources.get('resources', []):
            images.append({'public_id': r['public_id'], 'url': r['secure_url']})
        return jsonify({"images": images})
    except Exception as e:
        print("Cloudinary list error:", e)
        return jsonify({"images":[]})

@app.route('/delete_image', methods=['POST'])
def delete_image():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    public_id = request.form.get('filename')
    if not public_id:
        return jsonify({"error":"No filename(public_id)"}), 400
    result = cloudinary.uploader.destroy(public_id)
    if result.get('result') == 'ok':
        return redirect(url_for('list_images'))
    else:
        return "Chyba pri mazaní obrázka", 500

@app.route('/add', methods=['GET','POST'])
def add_page():
    if not is_admin():
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    error = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '')
        visible_to = request.form.get('visible_to', 'All')
        selected_tag_ids = request.form.getlist('tag_ids')
        selected_tag_ids = [int(x) for x in selected_tag_ids]
        if not title:
            error = "Názov stránky nesmie byť prázdny"
        else:
            slug = generate_slug(title, c)
            try:
                # Vloženie novej stránky
                c.execute("""
                    INSERT INTO pages (title, content, visible_to, created_at, updated_at, slug)
                    VALUES (%s, %s, %s, NOW(), NOW(), %s)
                    RETURNING id
                """, (title, content, visible_to, slug))
                new_page_id = c.fetchone()[0]

                # Vloženie špeciálneho tagu 'stránka' (ak neexistuje)
                c.execute("SELECT id FROM tags WHERE name='stránka'")
                row_t = c.fetchone()
                if not row_t:
                    c.execute("INSERT INTO tags (name, color) VALUES ('stránka', '#cccccc') RETURNING id;")
                    page_tag_id = c.fetchone()[0]
                else:
                    page_tag_id = row_t[0]

                # page_tags pre novú stránku
                c.execute("INSERT INTO page_tags (page_id, tag_id) VALUES (%s, %s)", (new_page_id, page_tag_id))
                for t_id in selected_tag_ids:
                    c.execute("""
                        INSERT INTO page_tags (page_id, tag_id) VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (new_page_id, t_id))
                conn.commit()

                # Uloženie udalosti 'edit' do page_history
                user_id = session['user']['id']
                c.execute("""
                    INSERT INTO page_history (page_id, user_id, event_type)
                    VALUES (%s, %s, 'edit')
                """, (new_page_id, user_id))
                conn.commit()

                # Presmeruj na detail stránky
                return redirect(url_for('view_page', slug=slug))

            except Exception as e:
                conn.rollback()
                error = f"Chyba pri ukladaní: {str(e)}"

    # Načítanie všetkých tagov (okrem 'stránka'), aby sme ich vedeli zobraziť vo formulári (checkboxy)
    c.execute("SELECT id, name, color FROM tags WHERE name <> 'stránka' ORDER BY name;")
    all_tags = c.fetchall()
    return render_template('page_edit.html',
                           mode='add',
                           page=None,
                           all_tags=all_tags,
                           page_tags=[],
                           editing_page=True,
                           error=error)


@app.route('/edit/<slug>', methods=['GET','POST'])
def edit_page(slug):
    if not is_admin():
        return redirect(url_for('index'))

    conn = get_db()
    c = conn.cursor()

    # Načítanie stránky podľa slug
    c.execute("SELECT * FROM pages WHERE slug=%s", (slug,))
    page = c.fetchone()
    if not page:
        return "Stránka neexistuje", 404

    error = None
    page_id = page['id']

    # Načítame existujúce tagy (okrem 'stránka') pre checkboxy
    c.execute("""
        SELECT t.id
        FROM tags t
        JOIN page_tags pt ON pt.tag_id = t.id
        WHERE pt.page_id=%s AND t.name<>'stránka'
        ORDER BY t.name
    """, (page_id,))
    page_tags_ids = [r['id'] for r in c.fetchall()]

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '')
        visible_to = request.form.get('visible_to', 'All')
        selected_tag_ids = request.form.getlist('tag_ids')
        selected_tag_ids = [int(x) for x in selected_tag_ids]

        if not title:
            error = "Názov stránky nesmie byť prázdny"
        else:
            # Vygeneruj nový slug (ak sa zmenil title)
            new_slug = generate_slug(title, c, existing_id=page_id)
            try:
                # Update stránky
                c.execute("""
                    UPDATE pages
                    SET title=%s, content=%s, visible_to=%s, updated_at=NOW(), slug=%s
                    WHERE id=%s
                """, (title, content, visible_to, new_slug, page_id))

                # Vymažeme existujúce tagy (okrem 'stránka') a vložíme nové
                c.execute("""
                    DELETE FROM page_tags
                    USING tags
                    WHERE page_tags.tag_id = tags.id
                      AND tags.name <> 'stránka'
                      AND page_tags.page_id = %s
                """, (page_id,))
                for t_id in selected_tag_ids:
                    c.execute("""
                        INSERT INTO page_tags (page_id, tag_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (page_id, t_id))
                conn.commit()

                # Zaznamenať 'edit' do histórie
                user_id = session['user']['id']
                c.execute("""
                    INSERT INTO page_history (page_id, user_id, event_type)
                    VALUES (%s, %s, 'edit')
                """, (page_id, user_id))
                conn.commit()

                return redirect(url_for('view_page', slug=new_slug))
            except Exception as e:
                conn.rollback()
                error = f"Chyba pri ukladaní: {str(e)}"

    # Načítanie všetkých tagov (okrem 'stránka') pre zobrazenie
    c.execute("SELECT id, name, color FROM tags WHERE name <> 'stránka' ORDER BY name;")
    all_tags = c.fetchall()

    return render_template('page_edit.html',
                           mode='edit',
                           page=page,
                           all_tags=all_tags,
                           page_tags=page_tags_ids,
                           editing_page=True,
                           error=error)


@app.route('/delete_page', methods=['POST'])
def delete_page():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    page_id = request.form.get('page_id')
    if not page_id:
        return jsonify({"error":"page_id missing"}), 400
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM pages WHERE id=%s", (page_id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/page/<slug>')
def view_page(slug):
    if not is_logged_in():
        return redirect(url_for('auth'))
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT p.id, p.title, p.content, p.visible_to, p.slug,
               COALESCE(json_agg(json_build_object('tag_id', t.id, 'name', t.name, 'color', t.color)
                                 ORDER BY t.name) FILTER (WHERE t.name IS NOT NULL), '[]') as tags
        FROM pages p
        LEFT JOIN page_tags pt ON p.id = pt.page_id
        LEFT JOIN tags t ON pt.tag_id = t.id AND t.name <> 'stránka'
        WHERE p.slug=%s
        GROUP BY p.id;
    """, (slug,))
    row = c.fetchone()
    if not row:
        return "Stránka neexistuje", 404

    if row['visible_to'] == 'Admin' and not is_admin():
        return "Nemáte oprávnenie zobraziť túto stránku.", 403

    # ===== TU vložíme záznam do page_history (event 'view') =====
    user_id = session['user']['id']  # z session - pri Google OAuth je tam ID z DB
    page_id = row['id']
    c.execute("""
        INSERT INTO page_history (page_id, user_id, event_type)
        VALUES (%s, %s, 'view')
    """, (page_id, user_id))
    conn.commit()

    html_content = md.markdown(row['content'] or '', extensions=['extra'])
    html_content = process_images(html_content)

    return render_template('page_view.html',
                           page_id=row['id'],
                           title=row['title'],
                           content=html_content,
                           page_tags=row['tags'],
                           slug=row['slug'])

@app.route('/api/page_history/<int:page_id>')
def api_page_history(page_id):
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), 403
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT ph.event_time, ph.event_type,
               u.first_name, u.last_name
        FROM page_history ph
        JOIN users u ON ph.user_id = u.id
        WHERE ph.page_id = %s
        ORDER BY ph.event_time ASC
    """, (page_id,))
    rows = c.fetchall()

    history = []
    for r in rows:
        history.append({
            "event_time": r["event_time"].strftime("%Y-%m-%d %H:%M:%S"),  # formátovanie
            "event_type": r["event_type"],
            "first_name": r["first_name"],
            "last_name": r["last_name"]
        })

    return jsonify({"history": history})



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
