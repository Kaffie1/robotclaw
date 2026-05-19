import os
import jinja2
import argparse
import yaml

def render_template(template_file: str, output_file: str, config_file: str):
    """
    读取YAML配置文件，渲染Jinja2模板，并写入输出文件。
    """
    # 1. 设置Jinja2环境
    template_dir = os.path.dirname(os.path.abspath(template_file))
    template_loader = jinja2.FileSystemLoader(searchpath=template_dir)
    template_env = jinja2.Environment(loader=template_loader)

    # 2. 读取并解析YAML配置文件
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    # 3. 准备要传递给模板的上下文（context）字典
    # 直接将解析后的字典作为上下文传递给模板
    context = {
        'oak': config.get('oak', {}),
        'realsense_cameras': config.get('realsense_cameras', {}),
        'wrist_camera': config.get('wrist_camera', {})
    }

    # 4. 加载并渲染模板
    template = template_env.get_template(os.path.basename(template_file))
    output_text = template.render(context)

    # 5. 写入最终的配置文件
    with open(output_file, "w") as f:
        f.write(output_text)
    print(f"Configuration successfully generated at: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a Jinja2 template with a YAML config file.")
    parser.add_argument("--template", required=True, help="Path to the Jinja2 template file.")
    parser.add_argument("--output", required=True, help="Path to the output configuration file.")
    parser.add_argument("--config", required=True, help="Path to the YAML configuration file.")
    args = parser.parse_args()

    render_template(args.template, args.output, args.config)