"""
Simple login system test
"""
from app import app, db, User
from werkzeug.security import generate_password_hash
import tempfile
import os

print('Testing login system...')

# Create test database
db_fd, db_path = tempfile.mkstemp()
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['TESTING'] = True

with app.test_client() as client:
    with app.app_context():
        db.create_all()

        # Create test user with hashed password
        user = User(username='test', email='test@test.com', password=generate_password_hash('pass'), role='admin')
        db.session.add(user)
        db.session.commit()

        # Test 1: Protected route redirects to login
        resp = client.get('/base-stock')
        redirect_to_login = resp.status_code == 302 and '/login' in resp.headers.get('Location', '')
        print(f'✓ Protected route redirects to login: {redirect_to_login}')

        # Test 2: Login with correct credentials
        resp = client.post('/login', data={'username': 'test', 'password': 'pass'}, follow_redirects=False)
        login_success = resp.status_code == 302 and '/base-stock' in resp.headers.get('Location', '')
        print(f'✓ Login success redirects to base-stock: {login_success}')

        # Test 3: Now protected route is accessible
        resp = client.get('/base-stock')
        accessible_after_login = resp.status_code == 200
        print(f'✓ Protected route accessible after login: {accessible_after_login}')

        # Test 4: Logout
        resp = client.get('/logout', follow_redirects=False)
        logout_redirect = resp.status_code == 302 and '/login' in resp.headers.get('Location', '')
        print(f'✓ Logout redirects to login: {logout_redirect}')

        # Test 5: Protected route redirects again after logout
        resp = client.get('/base-stock')
        redirect_after_logout = resp.status_code == 302 and '/login' in resp.headers.get('Location', '')
        print(f'✓ Protected route redirects after logout: {redirect_after_logout}')

# Cleanup
os.close(db_fd)
os.unlink(db_path)
print('✓ All login tests completed!')