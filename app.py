import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
from werkzeug.utils import secure_filename
import markdown as md
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = 'verysecretkey'

DATABASE = os.path.join(os.path.dirname(__file__), 'data', 'pages.db')

USERS = {
    "example1@gmail.com": {"password": "Abcdefghij1", "role": "Admin"},
    "example2@gmail.com": {"password": "Abcdefghij1", "role": "Admin"},
    "example3@gmail.com": {"password": "Abcdefghij1", "role": "Player"},
    "example4@gmail.com": {"password": "Abcdefghij1", "role": "Player"},
    "example5@gmail.com": {"password": "Abcdefghij1", "role": "Player"},
}

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Pre vytvaranie tabuliek
    # Nova tabulka folders
    c.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    ''')
    # Uprava pages tabulky: folder uz nebude text, ale foreign key:
    c.execute('''
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL UNIQUE,
        folder_id INTEGER NOT NULL,
        content TEXT,
        visible_to TEXT NOT NULL,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
    )
    ''')
    # Skontrolujeme, ci mame aspon jeden folder
    c.execute("SELECT COUNT(*) FROM folders")
    count = c.fetchone()[0]
    if count == 0:
        # Vlozime defaultny folder
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

        # full size view
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
    for f_id, f_name in folder_rows:
        if is_admin():
            c.execute("SELECT title, id FROM pages WHERE folder_id=? ORDER BY title", (f_id,))
        else:
            c.execute("SELECT title, id FROM pages WHERE folder_id=? AND visible_to='All' ORDER BY title", (f_id,))
        pages = c.fetchall()
        folders.append((f_id, f_name, pages))
    return render_template('index.html', folders=folders)

@app.route('/page/<int:page_id>')
def view_page(page_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, folder_id, content, visible_to FROM pages WHERE id=?", (page_id,))
    page = c.fetchone()
    if not page:
        return "Stránka neexistuje", 404
    title, folder_id, content, visible_to = page
    if visible_to == 'Admin' and not is_admin():
        return "Nemáte oprávnenie zobraziť túto stránku.", 403
    
    html_content = md.markdown(content)
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

        # skontrolujeme unikatny nazov
        c.execute("SELECT COUNT(*) FROM pages WHERE title=?", (title,))
        count = c.fetchone()[0]
        if count > 0:
            error = "Stránka s týmto názvom už existuje!"
        else:
            c.execute("INSERT INTO pages (title, folder_id, content, visible_to, created_at, updated_at) VALUES (?,?,?,?,datetime('now'),datetime('now'))",
                      (title, folder_id, content, visible_to))
            conn.commit()
            return redirect(url_for('index'))

    return render_template('page_edit.html', mode='add', folders=folders, error=error)

@app.route('/edit/<int:page_id>', methods=['GET','POST'])
def edit_page(page_id):
    if not is_admin():
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, folder_id, content, visible_to FROM pages WHERE id=?", (page_id,))
    page = c.fetchone()
    if not page:
        return "Stránka neexistuje", 404

    # na nacitanie folderov
    c.execute("SELECT id, name FROM folders ORDER BY name")
    folders = c.fetchall()

    error = None

    if request.method == 'POST':
        title = request.form.get('title')
        folder_id = request.form.get('folder_id')
        content = request.form.get('content')
        visible_to = request.form.get('visible_to')

        # skontrolujeme ci sa nezrazia nazvy stránok
        c.execute("SELECT COUNT(*) FROM pages WHERE title=? AND id!=?", (title, page_id))
        count = c.fetchone()[0]
        if count > 0:
            error = "Stránka s týmto názvom už existuje!"
        else:
            c.execute("UPDATE pages SET title=?, folder_id=?, content=?, visible_to=?, updated_at=datetime('now') WHERE id=?",
                      (title, folder_id, content, visible_to, page_id))
            conn.commit()
            return redirect(url_for('view_page', page_id=page_id))
    return render_template('page_edit.html', mode='edit', page_id=page_id, page=page, folders=folders, error=error)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_unique_filename(filepath):
    base, ext = os.path.splitext(filepath)
    counter = 2
    new_filepath = filepath
    while os.path.exists(new_filepath):
        new_filepath = f"{base}_{counter}{ext}"
        counter += 1
    return new_filepath

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if not is_admin():
        return jsonify({"error":"Not allowed"}), 403
    if 'image' not in request.files:
        return jsonify({"error":"No file"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error":"No filename"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            unique_filename = get_unique_filename(os.path.join(UPLOAD_FOLDER, filename))
            fn = os.path.basename(unique_filename)
            file.save(unique_filename)
            url = url_for('static', filename='uploads/' + fn, _external=False)
            return jsonify({"url": url})
        else:
            file.save(filepath)
            url = url_for('static', filename='uploads/' + filename, _external=False)
            return jsonify({"url": url})
    else:
        return jsonify({"error":"File not allowed"}), 400

@app.route('/images')
def list_images():
    if not is_admin():
        return redirect(url_for('index'))
    images = os.listdir(UPLOAD_FOLDER)
    images = [img for img in images if allowed_file(img)]
    return render_template('images.html', images=images)

@app.route('/delete_image', methods=['POST'])
def delete_image():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    filename = request.form.get('filename')
    if not filename:
        return jsonify({"error":"No filename"}), 400
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return redirect(url_for('list_images'))
    else:
        return "Súbor neexistuje", 404

# Pridať priečinok (iba admin)
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
            # skontrolujeme unique
            c.execute("SELECT COUNT(*) FROM folders WHERE name=?", (name,))
            count = c.fetchone()[0]
            if count > 0:
                error = "Priečinok s týmto názvom už existuje."
            else:
                c.execute("INSERT INTO folders (name) VALUES (?)", (name,))
                conn.commit()
                return redirect(url_for('index'))
    return render_template('folder_edit.html', mode='add', error=error)

# Premenovať priečinok
@app.route('/rename_folder/<int:folder_id>', methods=['GET','POST'])
def rename_folder(folder_id):
    if not is_admin():
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM folders WHERE id=?", (folder_id,))
    folder = c.fetchone()
    if not folder:
        return "Priečinok neexistuje", 404
    old_name = folder[0]
    error = None
    if request.method == 'POST':
        new_name = request.form.get('name').strip()
        if new_name == '':
            error = "Názov priečinka nemôže byť prázdny."
        else:
            c.execute("SELECT COUNT(*) FROM folders WHERE name=? AND id!=?", (new_name, folder_id))
            count = c.fetchone()[0]
            if count > 0:
                error = "Priečinok s týmto názvom už existuje."
            else:
                c.execute("UPDATE folders SET name=? WHERE id=?", (new_name, folder_id))
                conn.commit()
                return redirect(url_for('index'))
    return render_template('folder_edit.html', mode='edit', folder_id=folder_id, old_name=old_name, error=error)

# Zmazať priečinok
@app.route('/delete_folder', methods=['POST'])
def delete_folder():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    folder_id = request.form.get('folder_id')
    if not folder_id:
        return "folder_id missing", 400
    conn = get_db()
    c = conn.cursor()
    # vymazeme priecinok a tym padom aj vsetky stranky v nom (ON DELETE CASCADE)
    c.execute("DELETE FROM folders WHERE id=?", (folder_id,))
    conn.commit()
    return redirect(url_for('index'))

# Zmazať stránku
@app.route('/delete_page', methods=['POST'])
def delete_page():
    if not is_admin():
        return jsonify({"error": "Not allowed"}), 403
    page_id = request.form.get('page_id')
    if not page_id:
        return "page_id missing", 400
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM pages WHERE id=?", (page_id,))
    conn.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)