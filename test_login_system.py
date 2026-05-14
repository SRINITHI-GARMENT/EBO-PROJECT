"""
Test script to verify login redirect logic works correctly
"""

from app import app, db, User
from werkzeug.security import generate_password_hash
import tempfile
import os

def test_login_redirect():
    """Test that login redirect works properly"""

    print("=" * 60)
    print("LOGIN REDIRECT SYSTEM TEST")
    print("=" * 60)

    # Create a test database
    db_fd, db_path = tempfile.mkstemp()
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            # Create all tables
            db.create_all()

            # Create a test user with hashed password
            test_user = User(
                username="testuser",
                email="test@example.com",
                password=generate_password_hash("testpass123"),
                role="admin"
            )
            db.session.add(test_user)
            db.session.commit()

            print("\n✓ Testing unprotected routes:")

            # Test login page is accessible
            response = client.get('/login')
            print(f"  - /login: {'✓ Accessible' if response.status_code == 200 else '✗ Blocked'}")

            # Test logout is accessible
            response = client.get('/logout')
            print(f"  - /logout: {'✓ Accessible' if response.status_code == 302 else '✗ Blocked'}")

            print("\n✓ Testing protected routes (should redirect to login):")

            protected_routes = [
                '/',
                '/base-stock',
                '/actual-stock',
                '/order-sheet',
                '/requirement-report',
                '/custom-order-generation',
                '/users',
                '/add-user'
            ]

            for route in protected_routes:
                response = client.get(route)
                redirected = response.status_code == 302 and '/login' in response.headers.get('Location', '')
                print(f"  - {route}: {'✓ Redirects to login' if redirected else '✗ Does not redirect'}")

            print("\n✓ Testing login functionality:")

            # Test invalid login
            response = client.post('/login', data={
                'username': 'wronguser',
                'password': 'wrongpass'
            }, follow_redirects=False)
            print(f"  - Invalid login: {'✓ Stays on login' if response.status_code == 200 else '✗ Unexpected behavior'}")

            # Test valid login
            response = client.post('/login', data={
                'username': 'testuser',
                'password': 'testpass123'
            }, follow_redirects=False)
            login_success = response.status_code == 302 and '/base-stock' in response.headers.get('Location', '')
            print(f"  - Valid login: {'✓ Redirects to base-stock' if login_success else '✗ Login failed'}")

            # Test accessing protected route after login
            if login_success:
                response = client.get('/base-stock')
                accessible = response.status_code == 200
                print(f"  - Protected route after login: {'✓ Accessible' if accessible else '✗ Still blocked'}")

            print("\n✓ Testing logout:")

            # Test logout
            response = client.get('/logout', follow_redirects=False)
            logout_redirect = response.status_code == 302 and '/login' in response.headers.get('Location', '')
            print(f"  - Logout: {'✓ Redirects to login' if logout_redirect else '✗ Logout failed'}")

            # Test accessing protected route after logout
            response = client.get('/base-stock')
            redirected_after_logout = response.status_code == 302 and '/login' in response.headers.get('Location', '')
            print(f"  - Protected route after logout: {'✓ Redirects to login' if redirected_after_logout else '✗ Still accessible'}")

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)

    print("\n" + "=" * 60)
    print("LOGIN SYSTEM VERIFICATION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_login_redirect()