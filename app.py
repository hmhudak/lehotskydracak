import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
import markdown as md
from bs4 import BeautifulSoup
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = 'verysecretkey'

DATABASE_URL = os.environ.get('DATABASE_URL')  # Nastavíte na Rendere v env variables
# Napr: DATABASE_URL=postgresql://pages_owner:M8cesI3RKlEY@ep-falling-mountain-a21vv6d2.eu-central-1.aws.neon.tech/pages?sslmode=require

USERS = {
    "example1@gmail.com": {"password": "Abcdefghij1", "role": "Admin"},
    "example2@gmail.com": {"password": "Abcdefghij1", "role": "Admin"},
    "example3@gmail.com": {"password": "Abcdefghij1", "role": "Player"},
    "example4@gmail.com": {"password": "Abcdefghij1", "role": "Player"},
    "example5@gmail.com": {"password": "Abcdefghij1", "role": "Player"},
}

def get_db():
    if not hasattr(g, 'db_conn'):
        g.db_conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return g.db_conn

@app.teardown_appcontext
def close_connection(exception):
    if hasattr(g, 'db_conn'):
        g.db_conn.close()

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Vytvorenie tabuliek (Postgres)
    c.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS pages (
        id SERIAL PRIMARY KEY,
        title TEXT UNIQUE NOT NULL,
        folder_id INTEGER NOT NULL,
        content TEXT,
        visible_to TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
    );
    ''')
    # Skontrolujeme aspon jeden folder
    c.execute("SELECT COUNT(*) FROM folders")
    count = c.fetchone()[0]
    if count == 0:
        c.execute("INSERT INTO folders (name) VALUES ('General')")
    conn.commit()

with app.app_context():
    init_db()

def is_logged_in():
    return 'user' in session

def is_admin():
    return is_logged_in() and session['user']['role'] == 'Admin'

def process_images(html):
    soup = BeautifulSoup(html, 'html.parser')
    imgs = soup.find_all('img')
    for img in imgs:
        alt = img.get('alt', '')
        parts = [p.strip() for p in alt.split('|')]
        base_alt = parts[0] if parts else ''
        scale = None
        caption = None
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

        img['alt'] = base_alt
        style = img.get('style', '')
        style += ' display:block; margin-left:auto; margin-right:auto; height:auto;'
        if scale:
            style += f' max-width:{scale}%;'
        else:
            style += ' max-width:100%;'
        img['style'] = style.strip()

        img['data-fullsrc'] = img.get('src', '')

        if caption:
            figure = soup.new_tag('figure', style="text-align:center;")
            img.replace_with(figure)
            figure.append(img)
            figcap = soup.new_tag('figcaption')
            figcap.string = caption
            figcap['style'] = "font-size:smaller;color:#555;margin-top:5px;"
            figure.append(figcap)

    return str(soup)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = USERS.get(email)
        if user and user['password'] == password:
            session['user'] = {"email": email, "role": user['role']}
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Nesprávny email alebo heslo.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not is_logged_in():
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name FROM folders ORDER BY name")
    folder_rows = c.fetchall()
    folders = []
    for f in folder_rows:
        f_id = f['id']
        f_name = f['name']
        if is_admin():
            c.execute("SELECT title, id FROM pages WHERE folder_id=%s ORDER BY title", (f_id,))
        else:
            c.execute("SELECT title, id FROM pages WHERE folder_id=%s AND visible_to='All' ORDER BY title", (f_id,))
        pages = c.fetchall()
        pages_list = [(p['title'], p['id']) for p in pages]
        folders.append((f_id, f_name, pages_list))
    return render_template('index.html', folders=folders)

@app.route('/page/<int:page_id>')
def view_page(page_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, folder_id, content, visible_to FROM pages WHERE id=%s", (page_id,))
    page = c.fetchone()
    if not page:
        return "Stránka neexistuje", 404
    title, folder_id, content, visible_to = page['title'], page['folder_id'], page['content'], page['visible_to']
    if visible_to == 'Admin' and not is_admin():
        return "Nemáte oprávnenie zobraziť túto stránku.", 403
    
    html_content = md.markdown(content, extensions=['extra'])
    html_content = process_images(html_content)

    return render_template('page_view.html', title=title, content=html_content, page_id=page_id)

@app.route('/add', methods=['GET','POST'])
def add_page():
    if not is_admin():
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name FROM folders ORDER BY name")
    folders = c.fetchall()
    error = None
    if request.method == 'POST':
        title = request.form.get('title')
        folder_id = request.form.get('folder_id')
        content = request.form.get('content')
        visible_to = request.form.get('visible_to')

        c.execute("SELECT COUNT(*) FROM pages WHERE title=%s", (title,))
        count = c.fetchone()[0]
        if count > 0:
            error = "Stránka s týmto názvom už existuje!"
        else:
            c.execute("INSERT INTO pages (title, folder_id, content, visible_to, created_at, updated_at) VALUES (%s,%s,%s,%s, NOW(), NOW())",
                      (title, folder_id, content, visible_to))
            conn.commit()
            return redirect(url_for('index'))

    return render_template('page_edit.html', mode='add', folders=[(f['id'],f['name']) for f in folders], error=error)

@app.route('/edit/<int:page_id>', methods=['GET','POST'])
def edit_page(page_id):
    if not is_admin():
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, folder_id, content, visible_to FROM pages WHERE id=%s", (page_id,))
    page = c.fetchone()
    if not page:
        return "Stránka neexistuje", 404

    c.execute("SELECT id, name FROM folders ORDER BY name")
    folders = c.fetchall()

    error = None

    if request.method == 'POST':
        title = request.form.get('title')
        folder_id = request.form.get('folder_id')
        content = request.form.get('content')
        visible_to = request.form.get('visible_to')

        c.execute("SELECT COUNT(*) FROM pages WHERE title=%s AND id!=%s", (title, page_id))
        count = c.fetchone()[0]
        if count > 0:
            error = "Stránka s týmto názvom už existuje!"
        else:
            c.execute("UPDATE pages SET title=%s, folder_id=%s, content=%s, visible_to=%s, updated_at=NOW() WHERE id=%s",
                      (title, folder_id, content, visible_to, page_id))
            conn.commit()
            return redirect(url_for('view_page', page_id=page_id))
    return render_template('page_edit.html', mode='edit', page_id=page_id, page=(page['title'], page['folder_id'], page['content'], page['visible_to']), folders=[(f['id'],f['name']) for f in folders], error=error)

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if not is_admin():
        return jsonify({"error":"Not allowed"}), 403
    if 'image' not in request.files:
        return jsonify({"error":"No file"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error":"No filename"}), 400

    # Voliteľné: skontrolujeme príponu
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    if not allowed_file(file.filename):
        return jsonify({"error":"File not allowed"}), 400

    result = cloudinary.uploader.upload(file, folder="lohotskydracak")

    if 'secure_url' in result:
        return jsonify({"url": result['secure_url']})
    else:
        return jsonify({"error":"Upload failed"}), 500

@app.route('/images')
def list_images():
    if not is_admin():
        return redirect(url_for('index'))
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    images = os.listdir(UPLOAD_FOLDER)
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    images = [img for img in images if allowed_file(img)]
    return render_template('images.html', images=images)

@app.route('/delete_image', methods=['POST'])
def delete_image():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    filename = request.form.get('filename')
    if not filename:
        return jsonify({"error":"No filename"}), 400
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return redirect(url_for('list_images'))
    else:
        return "Súbor neexistuje", 404

@app.route('/add_folder', methods=['GET','POST'])
def add_folder():
    if not is_admin():
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    error = None
    if request.method == 'POST':
        name = request.form.get('name').strip()
        if name == '':
            error = "Názov priečinka nemôže byť prázdny."
        else:
            c.execute("SELECT COUNT(*) FROM folders WHERE name=%s", (name,))
            count = c.fetchone()[0]
            if count > 0:
                error = "Priečinok s týmto názvom už existuje."
            else:
                c.execute("INSERT INTO folders (name) VALUES (%s)", (name,))
                conn.commit()
                return redirect(url_for('index'))
    return render_template('folder_edit.html', mode='add', error=error)

@app.route('/rename_folder/<int:folder_id>', methods=['GET','POST'])
def rename_folder(folder_id):
    if not is_admin():
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM folders WHERE id=%s", (folder_id,))
    folder = c.fetchone()
    if not folder:
        return "Priečinok neexistuje", 404
    old_name = folder['name']
    error = None
    if request.method == 'POST':
        new_name = request.form.get('name').strip()
        if new_name == '':
            error = "Názov priečinka nemôže byť prázdny."
        else:
            c.execute("SELECT COUNT(*) FROM folders WHERE name=%s AND id!=%s", (new_name, folder_id))
            count = c.fetchone()[0]
            if count > 0:
                error = "Priečinok s týmto názvom už existuje."
            else:
                c.execute("UPDATE folders SET name=%s WHERE id=%s", (new_name, folder_id))
                conn.commit()
                return redirect(url_for('index'))
    return render_template('folder_edit.html', mode='edit', folder_id=folder_id, old_name=old_name, error=error)

@app.route('/delete_folder', methods=['POST'])
def delete_folder():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    folder_id = request.form.get('folder_id')
    if not folder_id:
        return "folder_id missing", 400
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM folders WHERE id=%s", (folder_id,))
    conn.commit()
    return redirect(url_for('index'))

@app.route('/delete_page', methods=['POST'])
def delete_page():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    page_id = request.form.get('page_id')
    if not page_id:
        return "page_id missing", 400
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM pages WHERE id=%s", (page_id,))
    conn.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
