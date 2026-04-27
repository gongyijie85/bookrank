from app import create_app

app = create_app()

with app.app_context():
    from app.models.schemas import APICache
    
    # 检查所有 NYT 缓存
    nyt_caches = APICache.query.filter_by(api_source='nyt').all()
    
    print(f"Found {len(nyt_caches)} NYT cache entries")
    print("-" * 80)
    
    for cache in nyt_caches:
        print(f"Key: {cache.request_key}")
        print(f"Expires: {cache.expires_at}")
        print(f"Status: {cache.status_code}")
        print(f"Error: {cache.error_message}")
        print("-" * 80)
        
    # 专门检查 paperback-nonfiction
    pb_nonfiction = APICache.query.filter_by(api_source='nyt', request_key='paperback-nonfiction').first()
    if pb_nonfiction:
        print("\nPaperback Nonfiction cache found:")
        print(f"Status: {pb_nonfiction.status_code}")
        print(f"Error: {pb_nonfiction.error_message}")
    else:
        print("\nNo Paperback Nonfiction cache found")
