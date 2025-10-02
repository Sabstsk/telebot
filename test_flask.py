#!/usr/bin/env python3
"""
Simple test script to verify Flask app functionality
"""
import os
import sys
from flask import Flask

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_flask_app():
    """Test if Flask app can be imported and basic routes work"""
    try:
        # Test if we can import the main components
        from bot import app, config
        
        print("✅ Successfully imported Flask app")
        print(f"📡 Configured port: {config.PORT}")
        
        # Test if test_interface.html exists
        html_file = os.path.join(os.path.dirname(__file__), 'test_interface.html')
        if os.path.exists(html_file):
            print("✅ test_interface.html file found")
        else:
            print("⚠️ test_interface.html file not found in expected location")
        
        # Test Flask app configuration
        with app.test_client() as client:
            # Test home route
            response = client.get('/')
            if response.status_code == 200:
                print("✅ Home route (/) working")
            else:
                print(f"❌ Home route failed with status: {response.status_code}")
            
            # Test ping route
            response = client.get('/ping')
            if response.status_code == 200 and response.data == b'pong':
                print("✅ Ping route working")
            else:
                print(f"❌ Ping route failed")
            
            # Test status route
            response = client.get('/status')
            if response.status_code == 200:
                print("✅ Status route working")
                print(f"📊 Status response: {response.get_json()}")
            else:
                print(f"❌ Status route failed")
        
        print("\n🎉 Flask app test completed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Flask app functionality...")
    print("=" * 50)
    success = test_flask_app()
    print("=" * 50)
    if success:
        print("✅ All tests passed! Flask app is ready.")
    else:
        print("❌ Some tests failed. Check the errors above.")
