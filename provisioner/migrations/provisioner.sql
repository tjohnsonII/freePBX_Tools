-- 1 up
CREATE TABLE devices (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    mac           CHAR(12)     NOT NULL,
    vendor        VARCHAR(32)  NOT NULL,
    model         VARCHAR(64)  NULL,
    label         VARCHAR(128) NULL,
    extension     VARCHAR(32)  NULL,
    display_name  VARCHAR(128) NULL,
    sip_server    VARCHAR(128) NULL,
    sip_port      SMALLINT UNSIGNED NOT NULL DEFAULT 5060,
    sip_user      VARCHAR(64)  NULL,
    sip_password  VARCHAR(128) NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY devices_mac_uniq (mac)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE provisioning_requests (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    mac          CHAR(12)     NULL,
    path         VARCHAR(255) NOT NULL,
    remote_addr  VARCHAR(45)  NULL,
    user_agent   VARCHAR(255) NULL,
    matched      TINYINT(1)   NOT NULL DEFAULT 0,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY provisioning_requests_mac_idx (mac),
    KEY provisioning_requests_created_idx (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 1 down
DROP TABLE provisioning_requests;
DROP TABLE devices;
