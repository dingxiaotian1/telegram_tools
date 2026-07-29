-- =========================================================================
-- quarkF 频道 - 标签存储优化 SQL 脚本
-- =========================================================================
--
-- 【背景】
--   当前 tags 字段存储格式为 JSON 字符串（如 '["#科幻","#小说"]'），
--   这种存储方式在数据量增大后，按标签筛选时无法使用索引，性能会急剧下降。
--
-- 【优化方案】
--   新增 quarkF_tags 关联表，采用"多对多"关系模型：
--   - quarkF（主表）：保持不变，tags 字段作为冗余备份
--   - quarkF_tags（关联表）：存储 (message_id, tag_name) 对应关系
--
-- 【优势】
--   1. 按标签查询时可以使用索引，性能稳定
--   2. 可以轻松实现"热门标签排行"功能
--   3. 标签名去重存储，减少存储空间
--
-- 【兼容性】
--   修改 quarkF_sql.py 后，新写入数据时会同时写入关联表。
--   旧数据通过下方迁移脚本一次性处理。
--   查询时优先使用关联表，tags 字段作为降级查询的后备方案。
-- =========================================================================


-- ==================== 第一步：创建标签关联表 ====================
-- 【重点注释】此表存储每条消息的标签，message_id 关联主表
CREATE TABLE IF NOT EXISTS quarkF_tags (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    message_id BIGINT NOT NULL COMMENT '关联 quarkF 表的 message_id',
    tag_name VARCHAR(100) NOT NULL COMMENT '标签名称（含 # 号，如 #科幻）',
    INDEX idx_message_id (message_id) COMMENT '按消息ID查询索引',
    INDEX idx_tag_name (tag_name) COMMENT '按标签名查询索引'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='quarkF 频道标签关联表';


-- ==================== 第二步：迁移已有数据的标签 ====================
-- 【重点注释】将现有 quarkF 表中 tags 字段的 JSON 数据解析后写入关联表
-- 
-- 【实现思路】
--   使用 MySQL 的 JSON_TABLE 函数解析 JSON 数组，
--   将每个标签拆分为独立行后插入 quarkF_tags 表。
--   MySQL 8.0.4+ 支持 JSON_TABLE，如果版本低于 8.0，需要使用脚本来迁移。
--
-- 【注意事项】
--   1. 此语句只执行一次，用于初始化历史数据
--   2. 如果数据量很大（>10万条），建议分批执行
--   3. 执行前先备份数据库

-- MySQL 8.0+ 版本使用 JSON_TABLE（推荐）
INSERT IGNORE INTO quarkF_tags (message_id, tag_name)
SELECT 
    qt.message_id,
    jt.tag_name
FROM quarkF AS qt,
     JSON_TABLE(
         qt.tags,
         '$[*]' COLUMNS (
             tag_name VARCHAR(100) PATH '$'
         )
     ) AS jt
WHERE qt.tags IS NOT NULL AND qt.tags != '[]';


-- ==================== 第三步：建议添加的索引（主表） ====================
-- 【重点注释】优化 publish_time 字段的排序查询性能
ALTER TABLE quarkF ADD INDEX idx_publish_time (publish_time) COMMENT '发布时间索引，优化排序性能';


-- ==================== 降级方案（如果 MySQL 版本 < 8.0） ====================
-- 【重点注释】如果数据库版本不支持 JSON_TABLE，可以使用 Python 脚本迁移
-- 迁移脚本如下（保存为 migrate_tags.py）：
--
-- import pymysql
-- import json
--
-- conn = pymysql.connect(host='81.70.102.216', user='root', password='dingroot', db='telegram_channel')
-- cursor = conn.cursor()
--
-- # 查询所有有标签的数据
-- cursor.execute("SELECT message_id, tags FROM quarkF WHERE tags IS NOT NULL AND tags != '[]'")
-- rows = cursor.fetchall()
--
-- for message_id, tags_str in rows:
--     try:
--         tags = json.loads(tags_str)
--         for tag in tags:
--             cursor.execute("INSERT IGNORE INTO quarkF_tags (message_id, tag_name) VALUES (%s, %s)", (message_id, tag))
--     except:
--         pass
--
-- conn.commit()
-- cursor.close()
-- conn.close()
-- print(f"迁移完成，共处理 {len(rows)} 条记录")
