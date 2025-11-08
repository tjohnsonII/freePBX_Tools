
-- Sample SQL Queries for VPBX Database
-- Database: vpbx_data.db
-- Generated: 2025-11-08 10:33:44

-- ============================================================
-- BASIC QUERIES
-- ============================================================

-- 1. List all companies with Yealink phones
SELECT DISTINCT s.site_id, s.company_name, s.system_ip, s.freepbx_version
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
ORDER BY s.company_name;

-- 2. Count sites by phone vendor
SELECT vendor, COUNT(DISTINCT site_id) as site_count
FROM devices
WHERE vendor IS NOT NULL
GROUP BY vendor
ORDER BY site_count DESC;

-- 3. List all Yealink models in use
SELECT model, COUNT(*) as count
FROM devices
WHERE vendor = 'yealink'
GROUP BY model
ORDER BY count DESC;

-- 4. Find sites with specific phone models
SELECT s.site_id, s.company_name, d.model, COUNT(*) as phone_count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.model LIKE '%T46%'
GROUP BY s.site_id, s.company_name, d.model
ORDER BY phone_count DESC;

-- ============================================================
-- SECURITY QUERIES
-- ============================================================

-- 5. Sites with security issues
SELECT s.site_id, s.company_name, si.severity, COUNT(*) as issue_count
FROM sites s
JOIN security_issues si ON s.site_id = si.site_id
GROUP BY s.site_id, s.company_name, si.severity
ORDER BY 
    CASE si.severity 
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END,
    issue_count DESC;

-- 6. All critical security issues
SELECT s.site_id, s.company_name, s.system_ip, si.issue_type, si.description
FROM sites s
JOIN security_issues si ON s.site_id = si.site_id
WHERE si.severity = 'CRITICAL'
ORDER BY s.company_name;

-- ============================================================
-- VERSION QUERIES
-- ============================================================

-- 7. FreePBX version distribution
SELECT freepbx_version, COUNT(*) as count
FROM sites
WHERE freepbx_version IS NOT NULL AND freepbx_version != ''
GROUP BY freepbx_version
ORDER BY count DESC;

-- 8. Sites running old FreePBX versions
SELECT site_id, company_name, system_ip, freepbx_version, asterisk_version
FROM sites
WHERE freepbx_major < '15'
ORDER BY freepbx_major, company_name;

-- 9. Sites by platform
SELECT platform, COUNT(*) as count
FROM sites
GROUP BY platform
ORDER BY count DESC;

-- ============================================================
-- DEVICE QUERIES
-- ============================================================

-- 10. Total devices per site
SELECT s.site_id, s.company_name, COUNT(d.id) as device_count
FROM sites s
LEFT JOIN devices d ON s.site_id = d.site_id
GROUP BY s.site_id, s.company_name
HAVING device_count > 0
ORDER BY device_count DESC
LIMIT 20;

-- 11. Sites with mixed vendor phones
SELECT s.site_id, s.company_name, 
       GROUP_CONCAT(DISTINCT d.vendor) as vendors,
       COUNT(DISTINCT d.vendor) as vendor_count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor IS NOT NULL
GROUP BY s.site_id, s.company_name
HAVING vendor_count > 1
ORDER BY vendor_count DESC, s.company_name;

-- 12. Most common phone models across all sites
SELECT vendor, model, COUNT(*) as deployment_count
FROM devices
WHERE vendor IS NOT NULL AND model IS NOT NULL
GROUP BY vendor, model
ORDER BY deployment_count DESC
LIMIT 20;

-- ============================================================
-- COMPANY QUERIES
-- ============================================================

-- 13. Search for companies by name
SELECT site_id, company_name, system_ip, freepbx_version
FROM sites
WHERE company_name LIKE '%Medical%'
ORDER BY company_name;

-- 14. Sites by company handle (reseller/partner)
SELECT company_handle, COUNT(*) as site_count
FROM sites
WHERE company_handle IS NOT NULL
GROUP BY company_handle
ORDER BY site_count DESC;

-- 15. All information for a specific company
SELECT s.*, 
       (SELECT COUNT(*) FROM devices WHERE site_id = s.site_id) as device_count,
       (SELECT COUNT(*) FROM security_issues WHERE site_id = s.site_id) as security_issue_count
FROM sites s
WHERE s.company_name = '123.Net, LLC';

-- ============================================================
-- ADVANCED QUERIES
-- ============================================================

-- 16. Sites with Yealink AND security issues
SELECT s.site_id, s.company_name, s.system_ip,
       COUNT(DISTINCT d.id) as yealink_phones,
       COUNT(DISTINCT si.id) as security_issues
FROM sites s
JOIN devices d ON s.site_id = d.site_id
JOIN security_issues si ON s.site_id = si.site_id
WHERE d.vendor = 'yealink'
GROUP BY s.site_id, s.company_name, s.system_ip
ORDER BY security_issues DESC, s.company_name;

-- 17. Sites missing FreePBX version info
SELECT site_id, company_name, system_ip, platform
FROM sites
WHERE (freepbx_version IS NULL OR freepbx_version = '')
  AND platform != 'Unknown'
ORDER BY company_name;

-- 18. Largest Yealink deployments
SELECT s.site_id, s.company_name, s.system_ip,
       COUNT(d.id) as yealink_count,
       GROUP_CONCAT(DISTINCT d.model) as models
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
GROUP BY s.site_id, s.company_name, s.system_ip
ORDER BY yealink_count DESC
LIMIT 20;

-- 19. Export Yealink sites to CSV format
SELECT s.site_id, s.company_name, s.system_ip, d.model, d.mac_address
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
ORDER BY s.company_name, d.model;

-- 20. Sites with conference phones (CP models)
SELECT s.site_id, s.company_name, d.model, COUNT(*) as count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.model LIKE 'CP%'
GROUP BY s.site_id, s.company_name, d.model
ORDER BY count DESC, s.company_name;
