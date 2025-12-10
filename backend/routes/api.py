"""API 路由"""
import json
import os
import zipfile
import io
from flask import Blueprint, request, jsonify, Response, send_file
from backend.services.outline import get_outline_service
from backend.services.image import get_image_service
from backend.services.history import get_history_service
from backend.services.config import get_config_service

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/outline', methods=['POST'])
def generate_outline():
    """生成大纲（支持图片上传）"""
    try:
        # 检查是否是 multipart/form-data（带图片）
        if request.content_type and 'multipart/form-data' in request.content_type:
            topic = request.form.get('topic')
            # 获取上传的图片
            images = []
            if 'images' in request.files:
                files = request.files.getlist('images')
                for file in files:
                    if file and file.filename:
                        image_data = file.read()
                        images.append(image_data)
        else:
            # JSON 请求（无图片或 base64 图片）
            data = request.get_json()
            topic = data.get('topic')
            # 支持 base64 格式的图片
            images_base64 = data.get('images', [])
            images = []
            if images_base64:
                import base64
                for img_b64 in images_base64:
                    # 移除可能的 data URL 前缀
                    if ',' in img_b64:
                        img_b64 = img_b64.split(',')[1]
                    images.append(base64.b64decode(img_b64))

        if not topic:
            return jsonify({
                "success": False,
                "error": "参数错误：topic 不能为空。\\n请提供要生成图文的主题内容。"
            }), 400

        # 调用大纲生成服务
        outline_service = get_outline_service()
        result = outline_service.generate_outline(topic, images if images else None)

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        return jsonify({
            "success": False,
            "error": f"大纲生成异常。\\n错误详情: {error_msg}\\n建议：检查后端日志获取更多信息"
        }), 500


@api_bp.route('/generate', methods=['POST'])
def generate_images():
    """生成图片（SSE 流式返回，支持用户上传参考图片）"""
    try:
        # JSON 请求
        data = request.get_json()
        pages = data.get('pages')
        task_id = data.get('task_id')
        full_outline = data.get('full_outline', '')
        user_topic = data.get('user_topic', '')  # 用户原始输入
        # 支持 base64 格式的用户参考图片
        user_images_base64 = data.get('user_images', [])
        user_images = []
        if user_images_base64:
            import base64
            for img_b64 in user_images_base64:
                if ',' in img_b64:
                    img_b64 = img_b64.split(',')[1]
                user_images.append(base64.b64decode(img_b64))

        if not pages:
            return jsonify({
                "success": False,
                "error": "参数错误：pages 不能为空。\\n请提供要生成的页面列表数据。"
            }), 400

        # 获取图片生成服务
        image_service = get_image_service()

        def generate():
            """SSE 生成器"""
            for event in image_service.generate_images(
                pages, task_id, full_outline,
                user_images=user_images if user_images else None,
                user_topic=user_topic
            ):
                event_type = event["event"]
                event_data = event["data"]

                # 格式化为 SSE 格式
                yield f"event: {event_type}\\n"
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\\n\\n"

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )

    except Exception as e:
        error_msg = str(e)
        return jsonify({
            "success": False,
            "error": f"图片生成异常。\\n错误详情: {error_msg}\\n建议：检查图片生成服务配置和后端日志"
        }), 500


@api_bp.route('/images/<task_id>/<filename>', methods=['GET'])
def get_image(task_id, filename):
    """获取图片（支持缩略图）"""
    try:
        # 检查是否请求缩略图
        thumbnail = request.args.get('thumbnail', 'true').lower() == 'true'

        # 直接构建路径，不需要初始化 ImageService
        history_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "history"
        )

        if thumbnail:
            # 尝试返回缩略图
            thumb_filename = f"thumb_{filename}"
            thumb_filepath = os.path.join(history_root, task_id, thumb_filename)

            # 如果缩略图存在，返回缩略图
            if os.path.exists(thumb_filepath):
                return send_file(thumb_filepath, mimetype='image/png')

        # 返回原图
        filepath = os.path.join(history_root, task_id, filename)

        if not os.path.exists(filepath):
            return jsonify({
                "success": False,
                "error": f"图片不存在：{task_id}/{filename}"
            }), 404

        return send_file(filepath, mimetype='image/png')

    except Exception as e:
        error_msg = str(e)
        return jsonify({
            "success": False,
            "error": f"获取图片失败: {error_msg}"
        }), 500


@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "success": True,
        "message": "服务正常运行"
    }), 200