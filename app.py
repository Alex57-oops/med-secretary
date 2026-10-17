from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from datetime import datetime, timedelta
from gigachat_service import generate_documents
from speech_service import recognize_audio
from auth_service import (
    init_db, create_user, authenticate, get_user_by_email,
    get_user_by_id, get_all_patients, get_all_doctors, get_all_users,
    update_user, add_analysis, get_patient_analyses, get_analysis, delete_analysis,
    add_notification, get_user_notifications, count_unread, mark_notification_read, mark_all_read
)
import os
import json
import uuid
import base64
import io
import qrcode

app = Flask(__name__)
app.secret_key = 'ai-doctor-secret-key-2026'


# ===== ИНИЦИАЛИЗАЦИЯ =====
init_db()


def _seed_default_users():
    if not get_user_by_email('doctor@clinic.ru'):
        create_user('doctor@clinic.ru', 'doctor', 'doctor',
                    'Козлов Дмитрий Андреевич',
                    clinic='ГБУЗ «Городская клиническая больница №1», г. Самара',
                    speciality='Врач-терапевт')
    if not get_user_by_email('head@clinic.ru'):
        create_user('head@clinic.ru', 'head', 'head_doctor',
                    'Смирнова Елена Петровна',
                    clinic='ГБУЗ «Городская клиническая больница №1», г. Самара',
                    speciality='Главный врач')
    if not get_user_by_email('admin@clinic.ru'):
        create_user('admin@clinic.ru', 'admin', 'admin',
                    'Администратор Системы')
    if not get_user_by_email('ivanov@mail.ru'):
        create_user('ivanov@mail.ru', 'patient', 'patient',
                    'Иванов Иван Иванович',
                    card='001-2025', age=54, gender='М',
                    diagnosis='Гипертоническая болезнь II ст.')
    if not get_user_by_email('petrova@mail.ru'):
        create_user('petrova@mail.ru', 'patient', 'patient',
                    'Петрова Анна Сергеевна',
                    card='002-2025', age=38, gender='Ж',
                    diagnosis='Хронический гастрит')
    if not get_user_by_email('sidorov@mail.ru'):
        create_user('sidorov@mail.ru', 'patient', 'patient',
                    'Сидоров Пётр Алексеевич',
                    card='003-2025', age=67, gender='М',
                    diagnosis='Сахарный диабет 2 типа')


_seed_default_users()


# ===== ВСПОМОГАТЕЛЬНЫЕ =====
def current_user():
    if not session.get('logged_in'):
        return None
    return get_user_by_id(session.get('user_id'))


def base_context(active):
    user = current_user()
    notif_count = count_unread(user['id']) if user else 0
    return {
        'active': active,
        'user': user,
        'doctor_name': user['full_name'] if user else '',
        'doctor_initials': user['initials'] if user else '',
        'notif_count': notif_count,
    }


def appointments_dir():
    path = os.path.join(os.path.dirname(__file__), 'storage', 'appointments')
    os.makedirs(path, exist_ok=True)
    return path


def analyses_dir():
    path = os.path.join(os.path.dirname(__file__), 'storage', 'analyses')
    os.makedirs(path, exist_ok=True)
    return path


def make_qr_base64(data):
    """Генерирует QR-код как base64 PNG."""
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')


def load_appointments(patient_id):
    folder = appointments_dir()
    result = []
    for filename in os.listdir(folder):
        if not filename.endswith('.json'):
            continue
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('patient_id') == str(patient_id):
                result.append(data)
        except Exception:
            continue
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result


def load_all_appointments():
    folder = appointments_dir()
    result = []
    for filename in os.listdir(folder):
        if not filename.endswith('.json'):
            continue
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f:
                result.append(json.load(f))
        except Exception:
            continue
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result


def load_doctor_appointments(doctor_id):
    folder = appointments_dir()
    result = []
    for filename in os.listdir(folder):
        if not filename.endswith('.json'):
            continue
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('doctor_id') == str(doctor_id):
                result.append(data)
        except Exception:
            continue
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result


def save_appointment(patient_id, doctor_id, clinic, transcript, documents):
    appointment_id = 'A-' + uuid.uuid4().hex[:8]
    record = {
        'id': appointment_id,
        'patient_id': str(patient_id),
        'doctor_id': str(doctor_id),
        'clinic': clinic or '',
        'created_at': datetime.now().isoformat(),
        'date_display': datetime.now().strftime('%d.%m.%Y %H:%M'),
        'transcript': transcript,
        'dialogue': documents.get('dialogue', ''),
        'soap': documents.get('soap', ''),
        'referrals': documents.get('referrals', ''),
        'prescriptions': documents.get('prescriptions', ''),
    }
    filepath = os.path.join(appointments_dir(), f'{appointment_id}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return appointment_id


# ===== МАРШРУТЫ =====

@app.route('/')
def index():
    user = current_user()
    if not user:
        return render_template('landing.html')
    role = user['role']
    if role == 'patient':
        return redirect(url_for('patient_home'))
    if role == 'head_doctor':
        return redirect(url_for('head_dashboard'))
    if role == 'admin':
        return redirect(url_for('admin_panel'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    email_value = ""
    if request.method == 'POST':
        email_value = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = authenticate(email_value, password)
        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            session['initials'] = user['initials']
            return redirect(url_for('index'))
        error = "Неверный email или пароль"
    return render_template('login.html', error=error, email_value=email_value)


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    form = {}
    if request.method == 'POST':
        form = request.form.to_dict()
        email = form.get('email', '').strip()
        password = form.get('password', '')
        role = form.get('role', 'doctor')
        full_name = form.get('full_name', '').strip()

        if not email or not password or not full_name:
            error = "Заполните email, пароль и ФИО"
        elif len(password) < 4:
            error = "Пароль должен быть минимум 4 символа"
        else:
            ok = create_user(
                email=email, password=password, role=role, full_name=full_name,
                clinic=form.get('clinic'),
                speciality=form.get('speciality'),
                phone=form.get('phone'),
                card=form.get('card'),
                age=int(form['age']) if form.get('age') else None,
                gender=form.get('gender'),
                diagnosis=form.get('diagnosis'),
            )
            if ok:
                return redirect(url_for('login'))
            error = "Пользователь с таким email уже существует"

    return render_template('register.html', error=error, form=form)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ===== ВРАЧ =====

@app.route('/dashboard')
def dashboard():
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return redirect(url_for('index'))

    today = datetime.now().strftime('%d.%m.%Y')
    patients = get_all_patients()
    my_appts = load_doctor_appointments(user['id'])

    today_iso = datetime.now().strftime('%Y-%m-%d')
    appts_today = sum(1 for a in my_appts if a.get('created_at', '').startswith(today_iso))

    MINUTES_PER_APPOINTMENT = 6
    minutes_saved = len(my_appts) * MINUTES_PER_APPOINTMENT
    if minutes_saved == 0:
        time_saved = "0 мин"
    elif minutes_saved < 60:
        time_saved = f"{minutes_saved} мин"
    else:
        time_saved = f"{minutes_saved // 60} ч {minutes_saved % 60} мин"

    stats = {
        "appointments_today": appts_today,
        "total_patients": len(patients),
        "documents_generated": len(my_appts),
        "time_saved": time_saved
    }
    ctx = base_context('dashboard')
    ctx.update({'today': today, 'stats': stats})
    return render_template('dashboard.html', **ctx)


@app.route('/patients')
def patient_list():
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return redirect(url_for('index'))
    ctx = base_context('patients')
    ctx['patients'] = get_all_patients()
    return render_template('patient_list.html', **ctx)


@app.route('/patient/<int:patient_id>')
def patient_detail(patient_id):
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return redirect(url_for('index'))
    patient = get_user_by_id(patient_id)
    if not patient or patient['role'] != 'patient':
        return redirect(url_for('patient_list'))
    ctx = base_context('patients')
    ctx['patient'] = patient
    ctx['appointments'] = load_appointments(patient_id)
    ctx['analyses'] = get_patient_analyses(patient_id)
    return render_template('patient_detail.html', **ctx)


@app.route('/patient/<int:patient_id>/appointment')
def appointment(patient_id):
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return redirect(url_for('index'))
    patient = get_user_by_id(patient_id)
    if not patient or patient['role'] != 'patient':
        return redirect(url_for('patient_list'))
    ctx = base_context('patients')
    ctx['patient'] = patient
    return render_template('appointment.html', **ctx)


@app.route('/patient/<int:patient_id>/appointment/process', methods=['POST'])
def appointment_process(patient_id):
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return jsonify({'error': 'Не авторизован'}), 401

    data = request.get_json(silent=True) or {}
    transcript = (data.get('transcript') or '').strip()
    if len(transcript) < 20:
        return jsonify({'error': 'Слишком короткий текст.'}), 400

    try:
        existing = data.get('existing_documents', None)
        docs = generate_documents(transcript, existing_documents=existing)
        return jsonify({
            'success': True,
            'dialogue': docs['dialogue'],
            'soap': docs['soap'],
            'referrals': docs['referrals'],
            'prescriptions': docs['prescriptions'],
        })
    except Exception as e:
        return jsonify({'error': f'Ошибка GigaChat: {str(e)}'}), 500


@app.route('/patient/<int:patient_id>/appointment/save', methods=['POST'])
def appointment_save(patient_id):
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return jsonify({'error': 'Не авторизован'}), 401

    data = request.get_json(silent=True) or {}
    documents = {
        'dialogue': data.get('dialogue', ''),
        'soap': data.get('soap', ''),
        'referrals': data.get('referrals', ''),
        'prescriptions': data.get('prescriptions', ''),
    }
    if not documents['soap']:
        return jsonify({'error': 'Нет документов для сохранения'}), 400

    try:
        aid = save_appointment(patient_id, user['id'], user.get('clinic'),
                               data.get('transcript', ''), documents)

        # Уведомление пациенту
        patient = get_user_by_id(patient_id)
        if patient:
            add_notification(
                patient_id,
                'new_appointment',
                '📄 Новый документ от врача',
                f'{user["full_name"]} оформил приём {aid}. Откройте, чтобы посмотреть SOAP, направления и рецепты.',
                f'/my/appointment/{aid}'
            )

        return jsonify({'success': True, 'appointment_id': aid})
    except Exception as e:
        return jsonify({'error': f'Ошибка сохранения: {str(e)}'}), 500


@app.route('/patient/<int:patient_id>/appointment/recognize', methods=['POST'])
def appointment_recognize(patient_id):
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return jsonify({'error': 'Не авторизован'}), 401

    if 'audio' not in request.files:
        return jsonify({'error': 'Файл не получен'}), 400

    audio_file = request.files['audio']
    if not audio_file.filename:
        return jsonify({'error': 'Пустой файл'}), 400

    ext = os.path.splitext(audio_file.filename)[1] or '.webm'
    temp_path = os.path.join(appointments_dir(), 'temp_audio' + ext)
    audio_file.save(temp_path)
    try:
        text = recognize_audio(temp_path)
        return jsonify({'success': True, 'text': text})
    except Exception as e:
        return jsonify({'error': f'Ошибка распознавания: {str(e)}'}), 500
    finally:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception: pass


@app.route('/appointment/<appointment_id>')
def appointment_view(appointment_id):
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return redirect(url_for('index'))

    filepath = os.path.join(appointments_dir(), f'{appointment_id}.json')
    if not os.path.exists(filepath):
        return redirect(url_for('dashboard'))
    with open(filepath, 'r', encoding='utf-8') as f:
        appointment = json.load(f)

    patient = get_user_by_id(int(appointment.get('patient_id', 0)))

    # QR-код для пациента
    qr_data = request.host_url.rstrip('/') + f'/my/appointment/{appointment_id}'
    qr_base64 = make_qr_base64(qr_data)

    ctx = base_context('patients')
    ctx['appointment'] = appointment
    ctx['patient'] = patient
    ctx['qr_base64'] = qr_base64
    return render_template('appointment_view.html', **ctx)


@app.route('/documents')
def documents():
    user = current_user()
    if not user or user['role'] not in ('doctor', 'head_doctor'):
        return redirect(url_for('index'))
    my_appts = load_doctor_appointments(user['id'])
    for a in my_appts:
        pid = int(a.get('patient_id', 0))
        patient = get_user_by_id(pid)
        a['patient_name'] = patient['full_name'] if patient else 'Неизвестный пациент'
        a['patient_card'] = patient['card'] if patient else '—'
    ctx = base_context('documents')
    ctx['appointments'] = my_appts
    return render_template('documents.html', **ctx)


@app.route('/profile')
def profile():
    user = current_user()
    if not user:
        return redirect(url_for('index'))
    return render_template('profile.html', **base_context('profile'))


@app.route('/profile/save', methods=['POST'])
def profile_save():
    user = current_user()
    if not user:
        return redirect(url_for('index'))

    update_user(
        user['id'],
        full_name=request.form.get('full_name', '').strip(),
        clinic=request.form.get('clinic', '').strip(),
        speciality=request.form.get('speciality', '').strip(),
        phone=request.form.get('phone', '').strip(),
        card=request.form.get('card', '').strip(),
        age=int(request.form['age']) if request.form.get('age') else None,
        gender=request.form.get('gender', '').strip(),
        diagnosis=request.form.get('diagnosis', '').strip(),
    )
    refreshed = get_user_by_id(user['id'])
    session['full_name'] = refreshed['full_name']
    session['initials'] = refreshed['initials']

    return redirect(url_for('profile', saved='1'))


# ===== ПАЦИЕНТ =====

@app.route('/my')
def patient_home():
    user = current_user()
    if not user or user['role'] != 'patient':
        return redirect(url_for('index'))
    appointments = load_appointments(user['id'])
    analyses = get_patient_analyses(user['id'])
    notifications = get_user_notifications(user['id'], only_unread=True)
    return render_template('patient_home.html',
                           user=user,
                           appointments=appointments,
                           analyses=analyses,
                           notifications=notifications)


@app.route('/my/appointment/<appointment_id>')
def patient_appointment(appointment_id):
    user = current_user()
    if not user or user['role'] != 'patient':
        return redirect(url_for('index'))

    filepath = os.path.join(appointments_dir(), f'{appointment_id}.json')
    if not os.path.exists(filepath):
        return redirect(url_for('patient_home'))
    with open(filepath, 'r', encoding='utf-8') as f:
        appointment = json.load(f)

    if appointment.get('patient_id') != str(user['id']):
        return redirect(url_for('patient_home'))

    return render_template('patient_appointment.html',
                           user=user, appointment=appointment)


@app.route('/my/notifications')
def patient_notifications():
    user = current_user()
    if not user or user['role'] != 'patient':
        return redirect(url_for('index'))
    notifications = get_user_notifications(user['id'])
    return render_template('patient_notifications.html',
                           user=user,
                           notifications=notifications)


@app.route('/my/notifications/read/<int:notif_id>')
def read_notification(notif_id):
    user = current_user()
    if not user:
        return redirect(url_for('index'))
    mark_notification_read(notif_id)
    return redirect(request.args.get('next', '/my'))


@app.route('/my/notifications/read-all')
def read_all_notifications():
    user = current_user()
    if not user:
        return redirect(url_for('index'))
    mark_all_read(user['id'])
    return redirect('/my')


@app.route('/my/upload-analysis', methods=['POST'])
def upload_analysis():
    user = current_user()
    if not user or user['role'] != 'patient':
        return redirect(url_for('index'))

    if 'file' not in request.files:
        return redirect(url_for('patient_home'))

    file = request.files['file']
    if not file.filename:
        return redirect(url_for('patient_home'))

    original_name = file.filename
    ext = os.path.splitext(original_name)[1].lower()
    unique_name = uuid.uuid4().hex + ext
    save_path = os.path.join(analyses_dir(), unique_name)
    file.save(save_path)

    title = request.form.get('title', '').strip() or 'Без названия'
    notes = request.form.get('notes', '').strip()

    if ext in ['.pdf']:
        file_type = 'pdf'
    elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        file_type = 'image'
    else:
        file_type = 'other'

    add_analysis(user['id'], unique_name, original_name, file_type, title, notes)
    return redirect(url_for('patient_home'))


@app.route('/my/analysis/<int:analysis_id>/view')
def view_analysis(analysis_id):
    user = current_user()
    if not user:
        return redirect(url_for('index'))

    analysis = get_analysis(analysis_id)
    if not analysis:
        return redirect(url_for('index'))

    if user['role'] == 'patient' and analysis['patient_id'] != user['id']:
        return redirect(url_for('index'))

    return send_from_directory(analyses_dir(), analysis['filename'],
                               download_name=analysis['original_name'])


@app.route('/my/analysis/<int:analysis_id>/delete', methods=['POST'])
def delete_my_analysis(analysis_id):
    user = current_user()
    if not user or user['role'] != 'patient':
        return redirect(url_for('index'))

    analysis = get_analysis(analysis_id)
    if not analysis or analysis['patient_id'] != user['id']:
        return redirect(url_for('patient_home'))

    filename = delete_analysis(analysis_id)
    if filename:
        path = os.path.join(analyses_dir(), filename)
        if os.path.exists(path):
            try: os.remove(path)
            except Exception: pass
    return redirect(url_for('patient_home'))


# ===== ГЛАВВРАЧ =====

@app.route('/head')
def head_dashboard():
    user = current_user()
    if not user or user['role'] != 'head_doctor':
        return redirect(url_for('index'))

    all_appts = load_all_appointments()
    doctors = get_all_doctors()
    patients = get_all_patients()

    doctor_stats = {}
    for doc in doctors:
        doctor_stats[doc['id']] = {
            'full_name': doc['full_name'],
            'speciality': doc.get('speciality', ''),
            'appointments': 0,
        }
    for a in all_appts:
        did = int(a.get('doctor_id', 0))
        if did in doctor_stats:
            doctor_stats[did]['appointments'] += 1

    # График: приёмы за последние 14 дней
    today = datetime.now().date()
    daily_stats = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        day_iso = day.strftime('%Y-%m-%d')
        count = sum(1 for a in all_appts if a.get('created_at', '').startswith(day_iso))
        daily_stats.append({
            'date': day.strftime('%d.%m'),
            'count': count,
        })

    # Максимум для масштабирования графика
    max_count = max([d['count'] for d in daily_stats]) or 1
    for d in daily_stats:
        d['height'] = int((d['count'] / max_count) * 100)

    # Топ врачей
    top_doctors = sorted(doctor_stats.values(), key=lambda x: -x['appointments'])[:5]

    # Метрики
    total_minutes_saved = len(all_appts) * 6
    if total_minutes_saved < 60:
        time_saved_total = f"{total_minutes_saved} мин"
    else:
        time_saved_total = f"{total_minutes_saved // 60} ч {total_minutes_saved % 60} мин"

    stats = {
        'total_appointments': len(all_appts),
        'total_doctors': len(doctors),
        'total_patients': len(patients),
        'time_saved_total': time_saved_total,
    }

    return render_template('head_dashboard.html',
                           user=user,
                           stats=stats,
                           doctor_stats=list(doctor_stats.values()),
                           daily_stats=daily_stats,
                           top_doctors=top_doctors,
                           recent_appointments=all_appts[:10])


# ===== АДМИН =====

@app.route('/admin')
def admin_panel():
    user = current_user()
    if not user or user['role'] != 'admin':
        return redirect(url_for('index'))
    return render_template('admin_panel.html',
                           user=user,
                           users=get_all_users())


# ===== ТЕСТ МИКРОФОНА =====

@app.route('/test-mic')
def test_mic():
    return render_template('test_mic.html')


if __name__ == '__main__':
            app.run(host='0.0.0.0', port=5000, debug=True)