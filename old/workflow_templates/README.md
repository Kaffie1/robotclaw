# Fault Workflows

每个故障一个目录，推荐结构如下：

```text
workflows/fault/<workflow_id>/
  playbook.yaml
  rules.yaml
  script.py        # 可选
  README.md        # 可选
```

新增 fault workflow 时，优先复制这两个模板：

- `workflow_templates/playbook.template.yaml`
- `workflow_templates/rules.template.yaml`

约定如下：

- `playbook.yaml` 现在推荐用行为树 `root` 来描述流程、工具调用、人工确认和结论分支。
- 旧 `script` 写法仍兼容，但新增 playbook 默认不要再使用旧格式。
- `rules.yaml` 负责描述断言规则和比较逻辑。
- 详细字段说明、输入输出说明、`confirmation` 写法、工具参数说明，都只写在对应模板文件顶部注释里。
- `README.md` 这里只保留目录结构和使用入口，不再重复维护详细参数文档。
