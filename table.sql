CREATE TABLE `quarkF` (
  `message_id` VARCHAR(64) NOT NULL COMMENT '主键，唯一，不自增',
  `title` VARCHAR(255) NOT NULL COMMENT '标题',
  `publish_time` DATETIME NULL COMMENT '发布时间',
  `image_info` TEXT NULL COMMENT '图片（多图存JSON数组）',
  `resource_desc` TEXT NULL COMMENT '资源简介',
  `link_url` VARCHAR(768) NOT NULL COMMENT '资源外部链接',
  `tags` VARCHAR(512) NULL COMMENT '标签，多标签逗号分隔',
  `original_content` LONGTEXT NULL COMMENT '原始完整内容',
  PRIMARY KEY (`message_id`),
  UNIQUE KEY `uk_link_url` (`link_url`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='夸克资源';

-- 此表存储每条消息的标签，message_id 关联主表
CREATE TABLE IF NOT EXISTS quarkF_tags (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    message_id VARCHAR(64) NOT NULL COMMENT '关联 quarkF 表的 message_id',
    tag_name VARCHAR(100) NOT NULL COMMENT '标签名称（含 # 号，如 #科幻）',
    INDEX idx_message_id (message_id) COMMENT '按消息ID查询索引',
    INDEX idx_tag_name (tag_name) COMMENT '按标签名查询索引'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='quarkF 频道标签关联表';
