

--
-- This file contains example SQL queries for analyzing the VPBX (Virtual PBX) database.
-- Each query is annotated with detailed comments explaining its purpose, logic, and usage.
-- The database schema includes: sites, devices, security_issues tables.
--

-- ============================================================
-- BASIC QUERIES
-- ============================================================

-- 1. List all companies with Yealink phones
--    Shows all sites that have at least one Yealink phone in their device inventory.
--    Useful for vendor-specific support, upgrades, or audits.
SELECT DISTINCT s.site_id, s.company_name, s.system_ip, s.freepbx_version
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
ORDER BY s.company_name;

-- 2. Count sites by phone vendor
--    Aggregates the number of unique sites for each phone vendor (brand).
--    Helps identify vendor market share across the fleet.
SELECT vendor, COUNT(DISTINCT site_id) as site_count
FROM devices
WHERE vendor IS NOT NULL
GROUP BY vendor
ORDER BY site_count DESC;

-- 3. List all Yealink models in use
--    Shows the count of each Yealink phone model deployed across all sites.
--    Useful for hardware lifecycle planning and support.
SELECT model, COUNT(*) as count
FROM devices
WHERE vendor = 'yealink'
GROUP BY model
ORDER BY count DESC;

-- 4. Find sites with specific phone models
--    Finds all sites using a particular phone model (e.g., T46 series).
--    Replace '%T46%' with another pattern to search for other models.
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
--    Lists all sites that have security issues, grouped by severity.
--    Useful for prioritizing remediation efforts.
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
--    Shows all sites with security issues marked as CRITICAL severity.
--    Use for urgent security response and compliance checks.
SELECT s.site_id, s.company_name, s.system_ip, si.issue_type, si.description
FROM sites s
JOIN security_issues si ON s.site_id = si.site_id
WHERE si.severity = 'CRITICAL'
ORDER BY s.company_name;

-- ============================================================
-- VERSION QUERIES
-- ============================================================

-- 7. FreePBX version distribution
--    Shows how many sites are running each version of FreePBX.
--    Useful for upgrade planning and version compliance.
SELECT freepbx_version, COUNT(*) as count
FROM sites
WHERE freepbx_version IS NOT NULL AND freepbx_version != ''
GROUP BY freepbx_version
ORDER BY count DESC;

-- 8. Sites running old FreePBX versions
--    Lists all sites running FreePBX major version less than 15.
--    Helps identify out-of-date or unsupported systems.
SELECT site_id, company_name, system_ip, freepbx_version, asterisk_version
FROM sites
WHERE freepbx_major < '15'
ORDER BY freepbx_major, company_name;

-- 9. Sites by platform
--    Shows the number of sites by hardware/software platform type.
--    Useful for platform migration or support planning.
SELECT platform, COUNT(*) as count
FROM sites
GROUP BY platform
ORDER BY count DESC;

-- ============================================================
-- DEVICE QUERIES
-- ============================================================

-- 10. Total devices per site
--     Lists the top 20 sites with the most devices deployed.
--     Useful for identifying large or complex deployments.
SELECT s.site_id, s.company_name, COUNT(d.id) as device_count
FROM sites s
LEFT JOIN devices d ON s.site_id = d.site_id
GROUP BY s.site_id, s.company_name
HAVING device_count > 0
ORDER BY device_count DESC
LIMIT 20;

-- 11. Sites with mixed vendor phones
--     Finds sites that have phones from more than one vendor (brand).
--     Useful for standardization or troubleshooting multi-vendor environments.
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
--     Lists the top 20 most widely deployed phone models, regardless of vendor.
--     Useful for inventory management and support focus.
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
--     Finds all sites where the company name matches a given pattern (e.g., contains 'Medical').
--     Edit the LIKE clause to search for other company names or keywords.
SELECT site_id, company_name, system_ip, freepbx_version
FROM sites
WHERE company_name LIKE '%Medical%'
ORDER BY company_name;

-- 14. Sites by company handle (reseller/partner)
--     Aggregates the number of sites managed by each company handle (reseller or partner).
--     Useful for partner management and reporting.
SELECT company_handle, COUNT(*) as site_count
FROM sites
WHERE company_handle IS NOT NULL
GROUP BY company_handle
ORDER BY site_count DESC;

-- 15. All information for a specific company
--     Shows all site fields, device count, and security issue count for a specific company.
--     Change the WHERE clause to target a different company name.
SELECT s.*, 
       (SELECT COUNT(*) FROM devices WHERE site_id = s.site_id) as device_count,
       (SELECT COUNT(*) FROM security_issues WHERE site_id = s.site_id) as security_issue_count
FROM sites s
WHERE s.company_name = '123.Net, LLC';

-- ============================================================
-- ADVANCED QUERIES
-- ============================================================

-- 16. Sites with Yealink AND security issues
--     Lists sites that have both Yealink phones and at least one security issue.
--     Useful for targeted remediation or vendor-specific risk analysis.
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
--     Finds sites where the FreePBX version is missing or blank, but platform is known.
--     Useful for data quality checks and inventory cleanup.
SELECT site_id, company_name, system_ip, platform
FROM sites
WHERE (freepbx_version IS NULL OR freepbx_version = '')
  AND platform != 'Unknown'
ORDER BY company_name;

-- 18. Largest Yealink deployments
--     Lists the top 20 sites with the most Yealink phones, including all models present.
--     Useful for vendor engagement or upgrade campaigns.
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
--     Exports all Yealink phone deployments with site, model, and MAC address info.
--     Useful for bulk provisioning or vendor audits.
SELECT s.site_id, s.company_name, s.system_ip, d.model, d.mac_address
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.vendor = 'yealink'
ORDER BY s.company_name, d.model;

-- 20. Sites with conference phones (CP models)
--     Lists all sites with conference phone models (model starts with 'CP').
--     Useful for identifying sites with special hardware needs.
SELECT s.site_id, s.company_name, d.model, COUNT(*) as count
FROM sites s
JOIN devices d ON s.site_id = d.site_id
WHERE d.model LIKE 'CP%'
GROUP BY s.site_id, s.company_name, d.model
ORDER BY count DESC, s.company_name;
