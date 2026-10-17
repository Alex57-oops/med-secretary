"""
Сервис аутентификации, пользователей, анализов и уведомлений.
"""

import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'storage', 'users.db')


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT NOT NULL,
            initials TEXT,
            clinic TEXT,
            speciality TEXT,
            phone TEXT,
            card TEXT,
            age INTEGER,
            gender TEXT,
            diagnosis TEXT,
            created_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            title TEXT,
            filename TEXT NOT NULL,
            original_name TEXT,
            file_type TEXT,
            notes TEXT,
            uploaded_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT,
            title TEXT,
            message TEXT,
            link TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()


def _initials(full_name):
    parts = full_name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return full_name[:2].upper()


def create_user(email, password, role, full_name, clinic=None, speciality=None,
                phone=None, card=None, age=None, gender=None, diagnosis=None):
    conn = _conn()
    try:
        conn.execute('''
            INSERT INTO users (email, password_hash, role, full_name, initials,
                               clinic, speciality, phone, card, age, gender, diagnosis, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            email.lower().strip(),
            generate_password_hash(password),
            role, full_name, _initials(full_name),
            clinic, speciality, phone, card, age, gender, diagnosis,
            datetime.now().isoformat()
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_user(user_id, **fields):
    allowed = ['full_name', 'initials', 'clinic', 'speciality', 'phone',
               'card', 'age', 'gender', 'diagnosis']
    updates = {k: v for k, v in fields.items() if k in allowed}
    if 'full_name' in updates and updates['full_name']:
        updates['initials'] = _initials(updates['full_name'])
    if not updates:
        return
    conn = _conn()
    sets = ', '.join([f'{k} = ?' for k in updates.keys()])
    values = list(updates.values()) + [user_id]
    conn.execute(f'UPDATE users SET {sets} WHERE id = ?', values)
    conn.commit()
    conn.close()


def authenticate(email, password):
    user = get_user_by_email(email)
    if not user:
        return None
    if check_password_hash(user['password_hash'], password):
        return user
    return None


def get_user_by_email(email):
    conn = _conn()
    row = conn.execute('SELECT * FROM users WHERE email = ?',
                       (email.lower().strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = _conn()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_patients():
    conn = _conn()
    rows = conn.execute("SELECT * FROM users WHERE role = 'patient' ORDER BY full_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_doctors():
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM users WHERE role IN ('doctor', 'head_doctor') ORDER BY full_name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_users():
    conn = _conn()
    rows = conn.execute("SELECT * FROM users ORDER BY role, full_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===== АНАЛИЗЫ =====

def add_analysis(patient_id, filename, original_name, file_type, title='', notes=''):
    conn = _conn()
    conn.execute('''
        INSERT INTO analyses (patient_id, title, filename, original_name,
                              file_type, notes, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (patient_id, title, filename, original_name, file_type, notes,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_patient_analyses(patient_id):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM analyses WHERE patient_id = ? ORDER BY uploaded_at DESC",
        (patient_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analysis(analysis_id):
    conn = _conn()
    row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_analysis(analysis_id):
    conn = _conn()
    row = conn.execute("SELECT filename FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    conn.commit()
    conn.close()
    return row['filename'] if row else None


# ===== УВЕДОМЛЕНИЯ =====

def add_notification(user_id, notif_type, title, message, link=''):
    conn = _conn()
    conn.execute('''
        INSERT INTO notifications (user_id, type, title, message, link, is_read, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
    ''', (user_id, notif_type, title, message, link, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_user_notifications(user_id, only_unread=False, limit=30):
    conn = _conn()
    if only_unread:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_unread(user_id):
    conn = _conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0",
        (user_id,)
    ).fetchone()
    conn.close()
    return row['cnt'] if row else 0


def mark_notification_read(notif_id):
    conn = _conn()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()


def mark_all_read(user_id):
    conn = _conn()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()