"""
Test RiceQuant Connection
==========================

Test different authentication methods for RiceQuant API
"""

import sys
import rqdatac

API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="

print("="*70)
print("RiceQuant Connection Test")
print("="*70)
print()

# Test 1: Try init without any parameters (if already configured)
print("Test 1: Init without parameters...")
try:
    rqdatac.init()
    print("  [OK] Connected!")
    
    # Try to fetch data
    df = rqdatac.get_price('RB888', start_date='2024-01-01', end_date='2024-01-10', frequency='1d')
    if df is not None and not df.empty:
        print(f"  [OK] Data fetched: {len(df)} records")
        print(df.head())
    else:
        print("  [Warning] No data returned")
except Exception as e:
    print(f"  [Failed] {e}")

print()

# Test 2: Try with username/password
print("Test 2: Init with username/password...")
try:
    # Common test credentials
    rqdatac.init(username="ricequant", password="ricequant")
    print("  [OK] Connected!")
    
    df = rqdatac.get_price('RB888', start_date='2024-01-01', end_date='2024-01-10', frequency='1d')
    if df is not None and not df.empty:
        print(f"  [OK] Data fetched: {len(df)} records")
except Exception as e:
    print(f"  [Failed] {e}")

print()

# Test 3: Try with extra_args
print("Test 3: Init with extra_args...")
try:
    rqdatac.init(username="ricequant", password="ricequant", 
                 extra_args={"api_key": API_KEY})
    print("  [OK] Connected!")
    
    df = rqdatac.get_price('RB888', start_date='2024-01-01', end_date='2024-01-10', frequency='1d')
    if df is not None and not df.empty:
        print(f"  [OK] Data fetched: {len(df)} records")
except Exception as e:
    print(f"  [Failed] {e}")

print()
print("="*70)
print("If all tests failed, please:")
print("  1. Check your RiceQuant account credentials")
print("  2. Verify API access is enabled for your account")
print("  3. Contact RiceQuant support for assistance")
print("  4. The system will use mock data as fallback")
print("="*70)
