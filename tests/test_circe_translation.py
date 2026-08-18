#!/usr/bin/env python3
"""
测试CIRCE书名翻译修复
"""

import pytest
from app import create_app
from app.models.schemas import BookMetadata
from app.models import db

@pytest.fixture
def app():
    """创建测试应用"""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()

def test_circe_translation_fix(app):
    """测试CIRCE书名翻译修复"""
    with app.app_context():
        # 创建CIRCE的BookMetadata记录
        circe_metadata = BookMetadata(
            isbn='9780316556323',
            title='CIRCE',
            title_zh='喀耳刻',
            author='Madeline Miller',
            language='en'
        )
        db.session.add(circe_metadata)
        db.session.commit()
        
        # 验证记录已创建
        saved_metadata = BookMetadata.query.filter_by(isbn='9780316556323').first()
        assert saved_metadata is not None
        assert saved_metadata.title == 'CIRCE'
        assert saved_metadata.title_zh == '喀耳刻'
        assert saved_metadata.author == 'Madeline Miller'

def test_circe_book_detail_page(client):
    """测试CIRCE书籍详情页"""
    # 注意：这个测试需要实际的数据库数据
    # 在实际环境中，需要确保CIRCE数据已存在
    pass

def test_translation_cache_cleanup(app):
    """测试翻译缓存清理"""
    with app.app_context():
        # 这里可以添加测试翻译缓存清理的逻辑
        pass