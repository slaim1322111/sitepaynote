from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'devkey')

# Конфигурация БД: используем PostgreSQL если переменная DATABASE_URL установлена (Docker),
# иначе используем SQLite (локальная разработка)
database_url = os.environ.get('DATABASE_URL')
if database_url:
	# PostgreSQL для Docker (полный URL)
	app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
	# Попробуем собрать DATABASE_URL из PG_* переменных (docker-compose .env)
	pg_user = os.environ.get('PG_USERNAME') or os.environ.get('PG_USER') or os.environ.get('POSTGRES_USER')
	pg_pass = os.environ.get('PG_PASSWORD') or os.environ.get('PG_PASS') or os.environ.get('POSTGRES_PASSWORD')
	pg_host = os.environ.get('PG_HOST') or os.environ.get('DB_HOST') or os.environ.get('POSTGRES_HOST')
	pg_port = os.environ.get('PG_PORT') or os.environ.get('POSTGRES_PORT') or '5432'
	pg_db = os.environ.get('PG_DATABASE') or os.environ.get('POSTGRES_DB')
	if pg_user and pg_pass and pg_host and pg_db:
		app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}'
	else:
		# SQLite для локальной разработки как fallback
		basedir = os.path.abspath(os.path.dirname(__file__))
		app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'notes_market.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Uploads configuration ---
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Limit uploads to 16 MB by default
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))

ALLOWED_EXTENSIONS = set(x.strip().lower() for x in os.environ.get('ALLOWED_EXTENSIONS', 'pdf,png,jpg,jpeg,zip,tif,tiff').split(','))

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.context_processor
def inject_now():
	"""Make a callable `now()` available in Jinja templates (returns UTC datetime)."""
	return { 'now': datetime.utcnow }


class Listing(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	title = db.Column(db.String(150), nullable=False)
	description = db.Column(db.Text)
	price = db.Column(db.Float, nullable=False)
	seller = db.Column(db.String(100))
	is_approved = db.Column(db.Boolean, default=False)
	file_name = db.Column(db.String(256), nullable=True)
	# New metadata fields
	genre = db.Column(db.String(80), nullable=True)
	composer = db.Column(db.String(120), nullable=True)
	tags = db.Column(db.String(255), nullable=True)  # comma-separated tags
	created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Purchase(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	listing_id = db.Column(db.Integer, db.ForeignKey('listing.id'), nullable=False)
	buyer = db.Column(db.String(100))
	purchased_at = db.Column(db.DateTime, default=datetime.utcnow)


class Review(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	listing_id = db.Column(db.Integer, db.ForeignKey('listing.id'), nullable=False)
	author = db.Column(db.String(80))
	rating = db.Column(db.Integer, nullable=False)
	comment = db.Column(db.Text)
	created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Favorite(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
	listing_id = db.Column(db.Integer, db.ForeignKey('listing.id'), nullable=False)
	created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CartItem(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
	listing_id = db.Column(db.Integer, db.ForeignKey('listing.id'), nullable=False)
	quantity = db.Column(db.Integer, default=1)
	added_at = db.Column(db.DateTime, default=datetime.utcnow)


class Message(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	sender = db.Column(db.String(80))
	email = db.Column(db.String(120))
	subject = db.Column(db.String(200))
	body = db.Column(db.Text)
	created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(db.Model, UserMixin):
	id = db.Column(db.Integer, primary_key=True)
	username = db.Column(db.String(80), unique=True, nullable=False)
	password_hash = db.Column(db.String(128), nullable=False)
	is_admin = db.Column(db.Boolean, default=False)
	balance = db.Column(db.Float, default=0.0)  # User balance in rubles

	def set_password(self, password):
		self.password_hash = generate_password_hash(password)

	def check_password(self, password):
		return check_password_hash(self.password_hash, password)


# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))


def init_db():
	"""Create database tables and seed initial data. Run inside app context."""
	db.create_all()
	
	# seed a couple of example listings
	translations = {
		"Moonlight Sonata (Piano) - Sheet": {
			'title': 'Лунная соната (фортепиано) — Ноты',
			'description': 'Качественное сканированное издание нот для первой части «Лунной сонаты» (Beethoven).',
			'price': 500.00,
		},
		"Guitar Riffs Collection": {
			'title': 'Сборник гитарных риффов',
			'description': 'Табы и аккорды на 20 классических риффов для гитары.',
			'price': 350.00,
		},
	}

	# Update existing listings that match English titles, or create them if no listings exist
	for eng_title, data in translations.items():
		existing = Listing.query.filter_by(title=eng_title).first()
		if existing:
			existing.title = data['title']
			existing.description = data['description']
			existing.price = data['price']
			db.session.add(existing)
		else:
			# if no listings at all, create new ones (avoid duplicating when DB already has other entries)
			if Listing.query.count() == 0:
				new = Listing(title=data['title'], description=data['description'], price=data['price'], seller='Alice' if 'Moonlight' in eng_title else 'Bob')
				db.session.add(new)

	# commit any changes
	db.session.commit()

	# Ensure required columns exist for current database dialect
	try:
		from sqlalchemy import text
		dialect = db.engine.dialect.name
		conn = db.engine.connect()
		if dialect == 'postgresql':
			# PostgreSQL supports IF NOT EXISTS for ALTER TABLE
			conn.execute(text("ALTER TABLE listing ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT false;"))
			conn.execute(text("ALTER TABLE listing ADD COLUMN IF NOT EXISTS file_name VARCHAR(256);"))
			conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false;'))
			conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS balance FLOAT DEFAULT 0.0;'))
		elif dialect == 'sqlite':
			# SQLite: use PRAGMA to inspect and ALTER if missing
			res = conn.execute(text("PRAGMA table_info('listing')"))
			listing_cols = [r[1] for r in res.fetchall()]
			if 'is_approved' not in listing_cols:
				conn.execute(text("ALTER TABLE listing ADD COLUMN is_approved BOOLEAN DEFAULT 0"))
			if 'file_name' not in listing_cols:
				conn.execute(text("ALTER TABLE listing ADD COLUMN file_name TEXT"))
			res = conn.execute(text("PRAGMA table_info('user')"))
			user_cols = [r[1] for r in res.fetchall()]
			if 'is_admin' not in user_cols:
				conn.execute(text("ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
			if 'balance' not in user_cols:
				conn.execute(text("ALTER TABLE user ADD COLUMN balance FLOAT DEFAULT 0.0"))
		conn.close()
	except Exception as e:
		print('Warning: schema migration step failed:', e)

	# Ensure an admin user exists (username=admin, password=admin) for convenience during development
	try:
		if not User.query.filter_by(username='admin').first():
			admin = User(username='admin')
			admin.set_password('admin')
			admin.is_admin = True
			db.session.add(admin)
			db.session.commit()
	except Exception as e:
		# best-effort: if DB is not ready or something else fails, skip silently
		print(f'Warning: Could not create admin user: {e}')


@app.route('/')
def index():
	# show only approved listings to general users
	q = request.args.get('q', '').strip()
	min_price = request.args.get('min_price')
	max_price = request.args.get('max_price')
	genre = request.args.get('genre', '').strip()
	composer = request.args.get('composer', '').strip()

	base_q = Listing.query
	if not (current_user.is_authenticated and getattr(current_user, 'is_admin', False)):
		base_q = base_q.filter_by(is_approved=True)

	if q:
		base_q = base_q.filter(Listing.title.ilike(f"%{q}%"))
	if genre:
		base_q = base_q.filter(Listing.genre.ilike(f"%{genre}%"))
	if composer:
		base_q = base_q.filter(Listing.composer.ilike(f"%{composer}%"))
	try:
		if min_price:
			base_q = base_q.filter(Listing.price >= float(min_price))
		if max_price:
			base_q = base_q.filter(Listing.price <= float(max_price))
	except ValueError:
		pass

	listings = base_q.order_by(Listing.created_at.desc()).all()
	return render_template('index.html', listings=listings)


@app.route('/listing/<int:listing_id>', methods=['GET', 'POST'])
def listing_detail(listing_id):
	listing = Listing.query.get_or_404(listing_id)
	# Check if user has purchased this listing
	user_has_purchased = False
	if current_user.is_authenticated:
		purchase = Purchase.query.filter_by(listing_id=listing.id, buyer=current_user.username).first()
		user_has_purchased = purchase is not None
	# Allow seller and admin to access file
	user_can_access_file = (
		user_has_purchased or
		(current_user.is_authenticated and current_user.username == listing.seller) or
		(current_user.is_authenticated and getattr(current_user, 'is_admin', False))
	)
	if request.method == 'POST':
		# if user is logged in, use their username; otherwise allow guest name
		if current_user.is_authenticated:
			buyer = current_user.username
			# Check if user has enough balance
			if current_user.balance < listing.price:
				flash(f'Недостаточно средств. Ваш баланс: ₽{current_user.balance:.2f}, требуется: ₽{listing.price:.2f}', 'danger')
				return render_template('listing.html', listing=listing, user_can_access_file=user_can_access_file)
			# Deduct from buyer's balance and add to seller's balance
			current_user.balance -= listing.price
			seller = User.query.filter_by(username=listing.seller).first()
			if seller:
				seller.balance += listing.price
		else:
			buyer = request.form.get('buyer', 'Аноним')
		purchase = Purchase(listing_id=listing.id, buyer=buyer)
		db.session.add(purchase)
		db.session.commit()
		flash(f'Спасибо, {buyer}! Вы приобрели "{listing.title}" за ₽{listing.price:.2f}', 'success')
		return redirect(url_for('checkout', purchase_id=purchase.id))
	return render_template('listing.html', listing=listing, user_can_access_file=user_can_access_file)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
	# serve uploaded files
	try:
		return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
	except Exception:
		abort(404)


@app.route('/listing/new', methods=['GET', 'POST'])
def new_listing():
	# require login to create listing
	if not current_user.is_authenticated:
		flash('Нужно войти, чтобы создать объявление.', 'warning')
		return redirect(url_for('login', next=url_for('new_listing')))

	if request.method == 'POST':
		title = request.form.get('title', '').strip()
		description = request.form.get('description', '').strip()
		price = request.form.get('price', '').strip()
		seller = current_user.username
		if not title or not price:
			flash('Заголовок и цена обязательны.', 'danger')
			return render_template('new_listing.html')
		try:
			price_val = float(price)
		except ValueError:
			flash('Цена должна быть числом.', 'danger')
			return render_template('new_listing.html')
		# handle file upload
		uploaded = request.files.get('file')
		filename = None
		if uploaded and uploaded.filename:
			name = secure_filename(uploaded.filename)
			ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
			if ext and ext in ALLOWED_EXTENSIONS:
				# unique filename
				unique_name = f"{int(datetime.utcnow().timestamp())}_{name}"
				save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
				uploaded.save(save_path)
				filename = unique_name
			else:
				flash('Недопустимый формат файла. Разрешены: ' + ','.join(sorted(ALLOWED_EXTENSIONS)), 'danger')
				return render_template('new_listing.html')

		listing = Listing(title=title, description=description, price=price_val, seller=seller, file_name=filename)
		db.session.add(listing)
		db.session.commit()
		flash('Объявление создано.', 'success')
		return redirect(url_for('listing_detail', listing_id=listing.id))
	return render_template('new_listing.html')


@app.route('/checkout/<int:purchase_id>')
def checkout(purchase_id):
	purchase = Purchase.query.get_or_404(purchase_id)
	listing = Listing.query.get(purchase.listing_id)
	return render_template('checkout.html', purchase=purchase, listing=listing)


@app.route('/register', methods=['GET', 'POST'])
def register():
	if request.method == 'POST':
		username = request.form.get('username', '').strip()
		password = request.form.get('password', '').strip()
		if not username or not password:
			flash('Имя пользователя и пароль обязательны.', 'danger')
			return render_template('register.html')
		if User.query.filter_by(username=username).first():
			flash('Пользователь с таким именем уже существует.', 'danger')
			return render_template('register.html')
		user = User(username=username)
		user.set_password(password)
		db.session.add(user)
		db.session.commit()
		flash('Регистрация успешна. Войдите в систему.', 'success')
		return redirect(url_for('login'))
	return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		username = request.form.get('username', '').strip()
		password = request.form.get('password', '').strip()
		user = User.query.filter_by(username=username).first()
		if user and user.check_password(password):
			login_user(user)
			flash('Вход выполнен.', 'success')
			next_page = request.args.get('next')
			return redirect(next_page or url_for('index'))
		flash('Неверные учётные данные.', 'danger')
	return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
	logout_user()
	flash('Вы вышли из системы.', 'info')
	return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
	# uploads: listings where seller == current_user.username
	uploads = Listing.query.filter_by(seller=current_user.username).order_by(Listing.created_at.desc()).all()
	# purchases: Purchase rows where buyer == current_user.username
	purchases_q = Purchase.query.filter_by(buyer=current_user.username).order_by(Purchase.purchased_at.desc()).all()
	# join purchases with listings for display
	purchases = []
	for p in purchases_q:
		listing = Listing.query.get(p.listing_id)
		if listing:
			purchases.append((p, listing))
	# If user is admin, provide pending listings for moderation
	pending = None
	if getattr(current_user, 'is_admin', False):
		pending = Listing.query.filter_by(is_approved=False).order_by(Listing.created_at.desc()).all()
	return render_template('dashboard.html', uploads=uploads, purchases=purchases, pending=pending)


@app.route('/admin/approve/<int:listing_id>')
@login_required
def approve_listing(listing_id):
	if not current_user.is_admin:
		flash('Доступ запрещён.', 'danger')
		return redirect(url_for('index'))
	listing = Listing.query.get_or_404(listing_id)
	listing.is_approved = True
	db.session.add(listing)
	db.session.commit()
	flash('Объявление одобрено.', 'success')
	return redirect(url_for('dashboard'))


@app.route('/admin/users')
@login_required
def admin_users():
	"""Admin panel to view and manage user balances"""
	if not current_user.is_admin:
		flash('Доступ запрещён.', 'danger')
		return redirect(url_for('index'))
	users = User.query.all()
	return render_template('admin_users.html', users=users)


@app.route('/admin/user/<int:user_id>/add-balance', methods=['POST'])
@login_required
def add_user_balance(user_id):
	"""Admin adds balance to user"""
	if not current_user.is_admin:
		flash('Доступ запрещён.', 'danger')
		return redirect(url_for('index'))
	user = User.query.get_or_404(user_id)
	amount = request.form.get('amount', '0')
	try:
		amount = float(amount)
		if amount <= 0:
			flash('Сумма должна быть положительной.', 'danger')
		else:
			user.balance += amount
			db.session.add(user)
			db.session.commit()
			flash(f'Добавлено ₽{amount:.2f} на счёт {user.username}. Новый баланс: ₽{user.balance:.2f}', 'success')
	except ValueError:
		flash('Некорректная сумма.', 'danger')
	return redirect(url_for('admin_users'))


@app.route('/admin/user/<int:user_id>/set-balance', methods=['POST'])
@login_required
def set_user_balance(user_id):
	"""Admin sets exact balance for user"""
	if not current_user.is_admin:
		flash('Доступ запрещён.', 'danger')
		return redirect(url_for('index'))
	user = User.query.get_or_404(user_id)
	amount = request.form.get('balance', '0')
	try:
		amount = float(amount)
		if amount < 0:
			flash('Баланс не может быть отрицательным.', 'danger')
		else:
			user.balance = amount
			db.session.add(user)
			db.session.commit()
			flash(f'Баланс {user.username} установлен на ₽{amount:.2f}', 'success')
	except ValueError:
		flash('Некорректная сумма.', 'danger')
	return redirect(url_for('admin_users'))


# Ensure DB schema is ready when the app is imported/run by a WSGI server
try:
	with app.app_context():
		init_db()
except Exception as e:
	# If DB init fails, print a warning but allow the app to continue starting
	print('Warning: init_db failed at import time:', e)

if __name__ == '__main__':
	# run development server
	app.run(host='0.0.0.0', port=5000, debug=True)


