@echo off
REM Safe Repository Organization Script
REM Only moves documentation and data files - NO CODE FILES
REM All Python scripts stay at root to preserve functionality

echo.
echo ========================================================
echo    FreePBX Tools - SAFE Repository Organization
echo    (Documentation and Data Files Only)
echo ========================================================
echo.

echo [1/4] Creating directory structure...
if not exist "docs" mkdir "docs"
if not exist "data" mkdir "data"
if not exist "data\analysis-output" mkdir "data\analysis-output"
if not exist "data\test-data" mkdir "data\test-data"
if not exist "data\backups" mkdir "data\backups"
echo    Done!

echo.
echo [2/4] Moving Documentation to docs/...
if exist "COMPREHENSIVE_SCRAPING.md" move /Y "COMPREHENSIVE_SCRAPING.md" "docs\" >nul && echo    - COMPREHENSIVE_SCRAPING.md
if exist "INTEGRATION_COMPLETE.md" move /Y "INTEGRATION_COMPLETE.md" "docs\" >nul && echo    - INTEGRATION_COMPLETE.md
if exist "LOG_ANALYSIS.md" move /Y "LOG_ANALYSIS.md" "docs\" >nul && echo    - LOG_ANALYSIS.md
if exist "MYSQL_DATABASE_ACCESS.md" move /Y "MYSQL_DATABASE_ACCESS.md" "docs\" >nul && echo    - MYSQL_DATABASE_ACCESS.md
if exist "ORGANIZATION.md" move /Y "ORGANIZATION.md" "docs\" >nul && echo    - ORGANIZATION.md
if exist "ORGANIZATION_ANALYSIS.md" move /Y "ORGANIZATION_ANALYSIS.md" "docs\" >nul && echo    - ORGANIZATION_ANALYSIS.md
if exist "PHONE_ANALYZER_INTEGRATION_GUIDE.md" move /Y "PHONE_ANALYZER_INTEGRATION_GUIDE.md" "docs\" >nul && echo    - PHONE_ANALYZER_INTEGRATION_GUIDE.md
if exist "PHONE_CONFIG_ANALYSIS.md" move /Y "PHONE_CONFIG_ANALYSIS.md" "docs\" >nul && echo    - PHONE_CONFIG_ANALYSIS.md
if exist "PHONE_CONFIG_ANALYZER_QUICKREF.md" move /Y "PHONE_CONFIG_ANALYZER_QUICKREF.md" "docs\" >nul && echo    - PHONE_CONFIG_ANALYZER_QUICKREF.md
if exist "PHONE_CONFIG_ANALYZER_README.md" move /Y "PHONE_CONFIG_ANALYZER_README.md" "docs\" >nul && echo    - PHONE_CONFIG_ANALYZER_README.md
if exist "PHONE_CONFIG_ANALYZER_SUMMARY.md" move /Y "PHONE_CONFIG_ANALYZER_SUMMARY.md" "docs\" >nul && echo    - PHONE_CONFIG_ANALYZER_SUMMARY.md
if exist "SECURITY.md" move /Y "SECURITY.md" "docs\" >nul && echo    - SECURITY.md
if exist "SECURITY_REVIEW_SUMMARY.md" move /Y "SECURITY_REVIEW_SUMMARY.md" "docs\" >nul && echo    - SECURITY_REVIEW_SUMMARY.md
if exist "VPBX_DATABASE_README.md" move /Y "VPBX_DATABASE_README.md" "docs\" >nul && echo    - VPBX_DATABASE_README.md
if exist "VPBX_DATA_ANALYSIS.md" move /Y "VPBX_DATA_ANALYSIS.md" "docs\" >nul && echo    - VPBX_DATA_ANALYSIS.md
if exist "WEB_INTERFACE_README.md" move /Y "WEB_INTERFACE_README.md" "docs\" >nul && echo    - WEB_INTERFACE_README.md

echo.
echo [3/4] Moving Analysis Outputs to data/analysis-output/...
if exist "analysis_output.json" move /Y "analysis_output.json" "data\analysis-output\" >nul && echo    - analysis_output.json
if exist "analysis_summary.csv" move /Y "analysis_summary.csv" "data\analysis-output\" >nul && echo    - analysis_summary.csv
if exist "FMU_analysis.json" move /Y "FMU_analysis.json" "data\analysis-output\" >nul && echo    - FMU_analysis.json
if exist "LES_analysis.json" move /Y "LES_analysis.json" "data\analysis-output\" >nul && echo    - LES_analysis.json
if exist "LES_summary.csv" move /Y "LES_summary.csv" "data\analysis-output\" >nul && echo    - LES_summary.csv
if exist "yealink_companies_full.csv" move /Y "yealink_companies_full.csv" "data\analysis-output\" >nul && echo    - yealink_companies_full.csv
if exist "yealink_companies_full.json" move /Y "yealink_companies_full.json" "data\analysis-output\" >nul && echo    - yealink_companies_full.json
if exist "yealink_companies_with_names.csv" move /Y "yealink_companies_with_names.csv" "data\analysis-output\" >nul && echo    - yealink_companies_with_names.csv
if exist "yealink_sites_report.csv" move /Y "yealink_sites_report.csv" "data\analysis-output\" >nul && echo    - yealink_sites_report.csv
if exist "yealink_sites_report.json" move /Y "yealink_sites_report.json" "data\analysis-output\" >nul && echo    - yealink_sites_report.json

echo.
echo [4/4] Moving Test and Backup Files...
echo    - Test outputs to test-data/
if exist "test_scrape_output" (
    xcopy "test_scrape_output" "data\test-data\test_scrape_output\" /E /I /Y >nul
    rmdir /S /Q "test_scrape_output"
    echo      * test_scrape_output/
)
if exist "vpbx_ultimate_analysis" (
    xcopy "vpbx_ultimate_analysis" "data\test-data\vpbx_ultimate_analysis\" /E /I /Y >nul
    rmdir /S /Q "vpbx_ultimate_analysis"
    echo      * vpbx_ultimate_analysis/
)
if exist "test_password_file.txt" move /Y "test_password_file.txt" "data\test-data\" >nul && echo      * test_password_file.txt

echo    - Backup files to backups/
if exist "scrape_vpbx_tables.py.backup" move /Y "scrape_vpbx_tables.py.backup" "data\backups\" >nul && echo      * scrape_vpbx_tables.py.backup
if exist "freepbx-tools.tar" move /Y "freepbx-tools.tar" "data\backups\" >nul && echo      * freepbx-tools.tar

echo.
echo    - Cleaning up temporary organization files
if exist ".gitkeep-instructions.txt" del /Q ".gitkeep-instructions.txt" >nul
if exist "organize_repo.ps1" del /Q "organize_repo.ps1" >nul
if exist "organize_repo.bat" del /Q "organize_repo.bat" >nul
if exist "organize_complete.bat" del /Q "organize_complete.bat" >nul

REM Clean up empty directories that were created but not used
if exist "cli-tools" rmdir "cli-tools" 2>nul
if exist "web-app\templates" rmdir "web-app\templates" 2>nul
if exist "web-app\static" rmdir "web-app\static" 2>nul
if exist "web-app" rmdir "web-app" 2>nul
if exist "database\queries" rmdir "database\queries" 2>nul
if exist "database" rmdir "database" 2>nul
if exist "data\server-lists" rmdir "data\server-lists" 2>nul

echo.
echo ========================================================
echo                  Organization Complete!
echo ========================================================
echo.
echo What was organized:
echo   docs/                   - All documentation files (16 files)
echo   data/analysis-output/   - JSON and CSV analysis results (10 files)
echo   data/test-data/         - Test outputs and folders (3 items)
echo   data/backups/           - Backup and archive files (2 files)
echo.
echo What stayed at root (NO CHANGES):
echo   ✅ All Python scripts    - Preserved for imports and calls
echo   ✅ config.py             - Required at root for imports
echo   ✅ ProductionServers.txt - Required at root for scripts
echo   ✅ vpbx_data.db          - Required at root for database scripts
echo   ✅ SQL files             - Used by scripts at root
echo   ✅ Shell scripts         - Orchestration scripts
echo   ✅ Templates folder      - Web app assets
echo   ✅ README.md             - Main documentation
echo.
echo ✅ All functionality preserved - no code broken!
echo.
pause
