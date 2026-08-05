import re

def quarkF_info(text):
    """
    quarkF
    FLMdongtianfudi
    """
    advertising = "Telegram必备的搜索引擎，极搜JISOU帮你精准找到，想要的群组、频道、视频、音乐"
    if not text:
        return {}, text, ""

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    title = lines[0] if lines else ""
    if advertising in title:
        return {}, "", ""

    # 提取下载链接
    links = re.findall(r'https?://[^\s]+', text)
    download_links = '\n'.join(links)

    # 提取标签
    tags = re.findall(r'#\w+', text)
    tags = list(set(tags))

    # 去掉标题行
    description = re.sub(r'^.*?\n', '', text, count=1).strip()

    # 去掉标签行、下载链接行、‼️ 行
    description = re.sub(r'🏷️.*?#.*?\n', '', description, flags=re.DOTALL)
    description = re.sub(r'🔗.*?(https?://[^\s]+)', '', description, flags=re.DOTALL)
    description = re.sub(r'‼️.*?(\n|$)', '', description, flags=re.DOTALL)
    description = re.sub(r'📝 资源介绍：\s*', '', description)

    # 清理多余空行
    description = re.sub(r'\n\s*\n', '\n\n', description).strip()

    # 去掉非内容行
    description = re.sub(r'\n\n.+$', '', description, flags=re.S).strip()

    record = {
        "标题": title,
        "资源简介": description,
        "链接": download_links,
        "标签": tags,
        "原始内容": text,
    }
    return record, title, download_links



def BooksRealm_info(text):
    """
    书之领域图书馆
    """
    advertising = "Telegram必备的搜索引擎"
    if not text:
        return {}, text, ""

    # ========== 1 提取标题  ==========
    title_match = re.search(r'标题：\s*(.*?)\s*\n', text, re.S)
    if title_match:
        title = title_match.group(1).strip()
    else:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        title = lines[0] if lines else ""
    if advertising in title:
        return {}, "", ""

    # ========== 2 提取链接 ==========
    link_match = re.search(r'链接：\s*(https?://\S+)', text)
    if link_match:
        download_links = link_match.group(1).strip()
    else:
        links = re.findall(r'https?://\S+', text)
        download_links = '\n'.join(links)

    # ==========3 提取全部标签 ==========
    tags = re.findall(r'#[^#\s\n]+', text)
    tags = list(set(tags))

    # ==========4 提取资源简介 ==========
    desc_match = re.search(r'简介：\s*(.*?)(?=\n链接：|\n🏷|\n👥|\Z)', text, re.S)
    if desc_match:
        description = desc_match.group(1).strip()
    else:
        # 没有简介标记，做旧逻辑兜底，剔除标题、链接、标签、群组等杂行
        temp = re.sub(r'^.*?\n', '', text, count=1).strip()
        # 删除标签行、链接行、群组行、特殊符号行
        temp = re.sub(r'🏷.*?(\n|$)', '', temp, flags=re.DOTALL)
        temp = re.sub(r'链接：.*?(https?://\S+)', '', temp, flags=re.DOTALL)
        temp = re.sub(r'👥.*?(\n|$)', '', temp, flags=re.DOTALL)
        temp = re.sub(r'‼️.*?(\n|$)', '', temp, flags=re.DOTALL)
        temp = re.sub(r'📝 资源介绍：\s*', '', temp)
        # 删掉末尾杂项（群组、频道广告）
        temp = re.sub(r'\n\n[^，。！？\w].+$', '', temp, flags=re.S)
        description = temp.strip()

    # 压缩多余空行
    description = re.sub(r'\n\s*\n+', '\n', description).strip()

    record = {
        "标题": title,
        "资源简介": description,
        "链接": download_links,
        "标签": tags,
        "原始内容": text,
    }
    return record, title, download_links
