"""邮件服务"""
import logging
from typing import List, Optional
from flask import current_app
from flask_mail import Mail, Message

logger = logging.getLogger(__name__)


class EmailService:
    """邮件服务类"""
    
    def __init__(self, mail: Mail):
        """初始化邮件服务
        
        Args:
            mail: Flask-Mail 实例
        """
        self.mail = mail
    
    def send_weekly_report_email(self, report, recipients: List[str]) -> bool:
        """发送周报邮件
        
        Args:
            report: 周报对象
            recipients: 收件人列表
            
        Returns:
            bool: 是否发送成功
        """
        try:
            from flask import render_template
            
            # 渲染邮件模板
            html_body = render_template('emails/weekly_report.html', report=report)
            
            # 创建邮件消息
            msg = Message(
                subject=f"【BookRank】{report.title}",
                recipients=recipients,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
                html=html_body
            )
            
            # 发送邮件
            self.mail.send(msg)
            logger.info(f"周报邮件发送成功: {report.title}, 收件人: {len(recipients)}")
            return True
            
        except Exception as e:
            logger.error(f"发送周报邮件失败: {str(e)}")
            return False
    
    def send_test_email(self, recipient: str) -> bool:
        """发送测试邮件
        
        Args:
            recipient: 收件人邮箱
            
        Returns:
            bool: 是否发送成功
        """
        try:
            msg = Message(
                subject="【BookRank】测试邮件",
                recipients=[recipient],
                sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
                html="<p>这是一封测试邮件，说明邮件发送功能正常。</p>"
            )
            
            self.mail.send(msg)
            logger.info(f"测试邮件发送成功: {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"发送测试邮件失败: {str(e)}")
            return False
    
    def is_email_configured(self) -> bool:
        """检查邮件配置是否完整
        
        Returns:
            bool: 配置是否完整
        """
        required_configs = [
            'MAIL_SERVER',
            'MAIL_PORT',
            'MAIL_USERNAME',
            'MAIL_PASSWORD'
        ]
        
        for config in required_configs:
            if not current_app.config.get(config):
                return False
        
        return True
