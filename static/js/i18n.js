/*
 * Olens i18n — bilingual EN/AR with RTL.
 *
 * Usage on an element:
 *   <span data-i18n="total_invoices">Total Invoices</span>
 *
 * Switch at runtime: window.olensI18n.set('ar' | 'en'). The saved
 * preference lives in localStorage under 'olens.lang' and is also
 * applied before first paint by the inline boot script in base.html
 * so there's no flash of the wrong language.
 *
 * Charts: Chart.js datasets carry labels in JS, not the DOM. Listen
 * for the 'olens:language-change' event and rebuild/update charts —
 * see the trend / payment-status / treemap call sites in financial.html.
 */
(function () {
  var STORAGE_KEY = 'olens.lang';

  var translations = {
    en: {
      // Sidebar sections
      overview:        'Overview',
      finance:         'Finance',
      inventory:       'Inventory',
      sales:           'Sales',
      human_resources: 'Human Resources',
      manufacturing:   'Manufacturing',

      // Sidebar nav items
      dashboard:   'Dashboard',
      invoices:    'Invoices',
      bills:       'Bills',
      banks:       'Banks',
      assets:      'Assets',
      expenses:    'Expenses',
      analytic:    'Analytic',
      financial_statements: 'Financial Statements',
      stock:       'Stock',
      movements:   'Movements',
      valuation:   'Valuation',
      pipeline:    'Pipeline',
      orders:      'Orders',
      attendance:  'Attendance',
      leave:       'Leave',
      production:  'Production',

      // Top bar / common buttons
      refresh:      'Refresh',
      logout:       'Logout',
      manual:       'Manual',
      min_5:        '5 min',
      min_15:       '15 min',
      min_30:       '30 min',
      theme:        'Theme',
      color_theme:  'COLOR THEME',
      company:      'Company',
      export_pdf:   'PDF',
      export_excel: 'Excel',
      apply:        'Apply',
      filter:       'Filter',
      clear_filters: 'Clear filters',
      clear_all:    'Clear All',
      search:       'Search',
      period:       'Period',
      from:         'From',
      to:           'To',
      show_amounts_in: 'SHOW AMOUNTS IN',
      compare_last_year: 'Compare with same period last year',
      overview_period: 'OVERVIEW PERIOD',

      // KPI cards (Invoices / Bills)
      total_invoices:    'Total Invoices',
      total_bills:       'Total Bills',
      total_amount:      'Total Amount',
      paid:              'Paid',
      outstanding:       'Outstanding',
      fully_settled:     'Fully settled',
      awaiting_payment:  'Awaiting payment',

      // Payment status
      payment_status:           'Payment Status',
      payment_status_dist:      'Payment Status Distribution',
      unpaid:                   'Unpaid',
      partial:                  'Partial',
      reversed:                 'Reversed',
      overdue:                  'Overdue',
      on_time:                  'On Time',
      no_overdue:               'No overdue',

      // Aging
      invoice_aging:      'Invoice Aging',
      bill_aging:         'Bill Aging',
      aging_distribution: 'Aging Distribution',
      period_days:        'Period (days)',

      // Periods
      today:         'Today',
      yesterday:     'Yesterday',
      last_7_days:   'Last 7 Days',
      this_month:    'This Month',
      last_month:    'Last Month',
      last_30_days:  'Last 30 Days',
      this_quarter:  'This Quarter',
      last_quarter:  'Last Quarter',
      last_6_months: 'Last 6 Months',
      last_90_days:  'Last 90 Days',
      this_year:     'This Year',
      ytd:           'Year to Date (YTD)',
      last_year:     'Last Year',
      last_2_years:  'Last 2 Years',
      last_365_days: 'Last 365 Days',
      all_time:      'All Time',
      custom:        'Custom',

      // Charts and sections
      collection_rate:      'Collection Rate Overview',
      invoice_trend:        'INVOICES TREND',
      bill_trend:           'BILLS TREND',
      tax_summary:          'TAX SUMMARY',
      total_untaxed:        'Total Untaxed',
      total_with_tax:       'Total with Tax',
      vat_collected:        'VAT Collected',
      vat_paid:             'VAT Paid',
      cash_flow_forecast:   'Cash Flow Forecast',
      based_on_today:       'Based on today — not affected by the period filter',
      next_30_days:         'Next 30 Days',
      total_expected:       'Total Expected',
      top_5_overdue:        'Top 5 Overdue',
      top_5_most_profitable: 'TOP 5 MOST PROFITABLE',
      top_5_least_profitable: 'TOP 5 LEAST PROFITABLE',

      // Tables
      invoice_num:    'Number',
      bill_num:       'Number',
      customer:       'Customer',
      vendor:         'Vendor',
      issue_date:     'Date',
      due_date:       'Due Date',
      amount:         'Amount',
      untaxed:        'Untaxed',
      tax:            'Tax',
      status:         'Status',
      payment:        'Payment',

      // Assets
      total_assets:           'Total Assets',
      acquisition_cost:       'Acquisition Cost',
      net_book_value:         'Net Book Value',
      accumulated_dep:        'Accumulated Dep.',
      depreciation_this_year: 'Depreciation This Year',
      fully_depreciated:      'Fully Depreciated',
      asset_name:             'Asset Name',
      asset_model:            'Asset Model',
      asset_account:          'Account',
      acquisition_date:       'Acquisition Date',
      original_value:         'Original Value',
      net_value:              'Net Value',
      assets_by_category:     'ASSETS BY CATEGORY',
      net_book_value_by_cat:  'NET BOOK VALUE BY CATEGORY',

      // Analytic
      cost_centers:            'Cost Centers',
      total_revenue:           'Total Revenue',
      total_costs:             'Total Costs',
      net_pl:                  'Net Profit / Loss',
      account_view:            'Account View',
      pl_accounts:             'P&L Accounts',
      balance_sheet:           'Balance Sheet Accounts',
      all_accounts:            'All Accounts',
      cost_center_dist:        'COST CENTER DISTRIBUTION',
      revenue_vs_cost:         'REVENUE vs COST PER CENTER',
      profitability_map:       'PROFITABILITY MAP',
      revenue:                 'Revenue',
      cost:                    'Cost',
      net:                     'Net',
      margin_pct:              'Margin %',

      // Banks
      bank_accounts:    'Bank Accounts',
      cash_balance:     'Cash Balance',
      reconciled:       'Reconciled',
      unreconciled:     'Unreconciled',

      // Dashboard
      welcome:                'Welcome',
      quick_stats:            'Quick Stats',
      module_overview:        'Module Overview',
      unpaid_invoices:        'Unpaid Invoices',
      open_sales_orders:      'Open Sales Orders',
      active_opportunities:   'Active Opportunities',
      stock_products:         'Stock Products',
      pending_leaves:         'Pending Leave Requests',
      active_employees:       'Active Employees',
      production_in_progress: 'Production In Progress',
      pending_expenses:       'Pending Expenses',
      monthly_revenue_6:      'Monthly Revenue (Last 6 Months)',
      invoice_payment_status: 'Invoice Payment Status',
      quick_access:           'Quick Access',
      sales_orders:           'Sales Orders',
      value_suffix:           'value',
      this_month_suffix:      'this month',

      // Inventory
      total_products:   'Total Products',
      total_value:      'Total Value',
      low_stock:        'Low Stock',
      out_of_stock:     'Out of Stock',
      stock_movements:  'Stock Movements',
      product:          'Product',
      quantity:         'Quantity',
      location:         'Location',

      // Sales
      total_orders:     'Total Orders',
      total_sales:      'Total Sales',
      quotations:       'Quotations',
      pipeline_value:   'Pipeline Value',
      order_number:     'Order #',
      salesperson:      'Salesperson',

      // HR
      total_employees:  'Total Employees',
      present:          'Present',
      absent:           'Absent',
      on_leave:         'On Leave',
      employee:         'Employee',
      check_in:         'Check In',
      check_out:        'Check Out',
      hours:            'Hours',
      leave_type:       'Leave Type',
      duration:         'Duration',

      // Manufacturing
      total_orders_mfg: 'Manufacturing Orders',
      in_progress:      'In Progress',
      done:             'Done',
      planned:          'Planned',
      reference:        'Reference',

      // Login
      login_title:      'Sign in to Olens',
      login_subtitle:   'Connect your Odoo instance',
      odoo_url:         'Odoo URL',
      database:         'Database',
      username:         'Username',
      api_key:          'API Key / Password',
      sign_in:          'Sign In',

      // Expenses / Banks
      total_expenses:        'Total Expenses',
      draft:                 'Draft',
      reported:              'Reported',
      approved_done:         'Approved / Done',
      bank_cash_accounts:    'Bank / Cash Accounts',
      statement_lines:       'Statement Lines',
      recent_transactions:   'Recent Transactions',
      in_payment:            'In Payment',
      filtered_fully_dep:    'Filtered: Fully Depreciated',
      description:           'Description',
      account:               'Account',
      start_date:            'Start Date',
      initial_amount:        'Initial Amount',
      remaining:             'Remaining',
      recognised:            'Recognised',
      total_def_expenses:    'Total Deferred Expenses',
      total_def_revenue:     'Total Deferred Revenue',
      no_invoices_found:     'No invoices found',
      no_bills_found:        'No bills found',
      no_records_found:      'No records found',
      no_data_to_chart:      'No category data to chart',
      no_analytic_data:      'No analytic data',
      // Additional HR keys
      total_records:         'Total Records',
      total_hours:           'Total Hours',
      present_today:         'Present Today',
      avg_hours_session:     'Avg Hours / Session',
      total_requests:        'Total Requests',
      pending_approval:      'Pending Approval',
      approved_days:         'Approved Days',
      refused:               'Refused',
      days:                  'Days',
      leave_status:          'Leave Status',
      active:                'Active',
      full_day:              'Full Day',
      half_day:              'Half Day',
      short:                 'Short',
      pending:               'Pending',
      second_approval:       '2nd Approval',
      approved:              'Approved',
      still_in:              'Still In',
      no_attendance_records: 'No attendance records found',
      no_leave_requests:     'No leave requests found',
      // Additional Inventory keys
      stock_lines:           'Stock Lines',
      total_stock_value:     'Total Stock Value',
      total_qty:             'Total Qty',
      zero_stock_lines:      'Zero Stock Lines',
      reserved:              'Reserved',
      available:             'Available',
      top_10_by_value:       'Top 10 by Value',
      total_moves:           'Total Moves',
      unit_cost:             'Unit Cost',
      valuation_layers:      'Valuation Layers',
      total_quantity:        'Total Quantity',
      qty:                   'Qty',
      no_stock_data:         'No stock data',
      no_movements:          'No movements',
      no_valuation_data:     'No valuation data',
      // Additional Sales keys
      confirmed:             'Confirmed',
      invoice:               'Invoice',
      monthly_revenue:       'Monthly Revenue',
      opportunities:         'Opportunities',
      expected_revenue:      'Expected Revenue',
      stages:                'Stages',
      opportunity:           'Opportunity',
      stage:                 'Stage',
      expected_rev:          'Expected Rev.',
      probability:           'Probability',
      deadline:              'Deadline',
      revenue_by_stage:      'Revenue by Stage',
      invoiced:              'Invoiced',
      to_invoice:            'To Invoice',
      nothing:               'Nothing',
      sent:                  'Sent',
      no_orders_found:       'No orders found',
      no_opportunities_found: 'No opportunities found',
      // Additional Manufacturing keys
      qty_produced:          'Qty Produced',
      planned_start:         'Planned Start',
      planned_end:           'Planned End',
      status_distribution:   'Status Distribution',
      summary:               'Summary',
      total_qty_produced:    'Total Qty Produced',
      to_close:              'To Close',
      cancelled:             'Cancelled',
      no_mo_found:           'No manufacturing orders found',
      // Additional Login keys
      odoo_analytics_platform: 'Odoo Analytics Platform',
      connect_to_odoo:       'Connect to Odoo',
      api_key_help:          'In Odoo: Settings → Technical → API Keys → Create',
      secure_xmlrpc:         'Secure XML-RPC connection',
      // Financial Statements
      fs_pnl:               'P&L',
      fs_pnl_full:          'Income Statement',
      fs_balance_sheet:     'Balance Sheet',
      fs_trial_balance:     'Trial Balance',
      fs_financial_ratios:  'Financial Ratios',
      fs_total_revenue:     'Total Revenue',
      fs_gross_profit:      'Gross Profit',
      fs_operating_profit:  'Operating Profit',
      fs_net_profit:        'Net Profit',
      fs_gross_margin:      'Gross Margin %',
      fs_net_margin:        'Net Margin %',
      fs_total_assets:      'Total Assets',
      fs_total_liabilities: 'Total Liabilities',
      fs_total_equity:      'Total Equity',
      fs_current_ratio:     'Current Ratio',
      fs_debt_equity:       'Debt to Equity',
      fs_working_capital:   'Working Capital',
      fs_total_debits:      'Total Debits',
      fs_total_credits:     'Total Credits',
      fs_difference:        'Difference',
      fs_total_accounts:    'Total Accounts',
      fs_assets:            'Assets',
      fs_liabilities_equity: 'Liabilities & Equity',
      fs_current_assets:    'Current Assets',
      fs_non_current_assets: 'Non-Current Assets',
      fs_current_liabilities: 'Current Liabilities',
      fs_non_current_liabilities: 'Non-Current Liabilities',
      fs_equity:            'Equity',
      fs_revenue:           'Revenue',
      fs_cost_of_revenue:   'Cost of Revenue',
      fs_operating_expenses: 'Operating Expenses',
      fs_other_income_expenses: 'Other Income / Expenses',
      fs_liquidity_ratios:  'Liquidity Ratios',
      fs_profitability_ratios: 'Profitability Ratios',
      fs_leverage_ratios:   'Leverage Ratios',
      fs_efficiency_ratios: 'Efficiency Ratios',
      fs_balanced:          'Balanced',
      fs_unbalanced:        'Unbalanced',
      fs_account_code:      'Account Code',
      fs_account_name:      'Account Name',
      fs_account_type:      'Type',
      fs_opening_debit:     'Opening Debit',
      fs_opening_credit:    'Opening Credit',
      fs_movement_debit:    'Movement Debit',
      fs_movement_credit:   'Movement Credit',
      fs_closing_debit:     'Closing Debit',
      fs_closing_credit:    'Closing Credit',
      fs_account:           'Account',
      fs_current_period:    'Current Period',
      fs_vs_last_year:      'vs Last Year',
      fs_change_pct:        'Change %',
      fs_pct_of_revenue:    '% of Revenue',
      fs_last_year:         'Last Year',
      fs_grand_total:       'Grand Total',
      fs_balance_check:     'Balance Check',
      fs_formula:           'Formula',
      fs_benchmark:         'Benchmark',
      fs_interpretation:    'Interpretation',
      fs_values:            'Values',
      fs_q1: 'Q1', fs_q2: 'Q2', fs_q3: 'Q3', fs_q4: 'Q4',
      // Account Mapping Settings drawer
      fs_settings:           'Settings',
      fs_account_mapping_title: 'Account Mapping Settings',
      fs_inventory_accounts: 'Inventory / Stock Accounts',
      fs_inventory_helper:   'Pick which asset_current accounts represent inventory.',
      fs_cash_accounts:      'Cash Only Accounts (excluding bank)',
      fs_cash_helper:        'Remaining asset_cash accounts will be treated as Bank.',
      fs_auto_detected:      'Auto-detected from Odoo account types',
      fs_auto_detected_note: "Liability classification follows Odoo's account_type — not user-editable.",
      fs_short_term_liab:    'Short-term Liabilities',
      fs_long_term_liab:     'Long-term Liabilities',
      fs_demo_mapping_note:  'In demo mode, mapping uses sample data.',
      fs_mapping_warning:    'Please configure Account Mapping for accurate ratio calculations.',
      fs_configure_now:      'Configure Now',
      fs_save:               'Save',
      cancel:                'Cancel',
      optional:              'optional',
      // Custom Ratio Builder
      fs_build_custom_ratio:  'Build Custom Ratio',
      fs_edit_custom_ratio:   'Edit Custom Ratio',
      fs_custom_badge:        'Custom',
      fs_custom_ratios:       'Custom Ratios',
      fs_step_basic:          'Basic',
      fs_step_formula:        'Formula',
      fs_step_display:        'Display',
      fs_step_benchmarks:     'Benchmarks',
      fs_step_interpretation: 'Interpretation',
      fs_step1_title:         'Step 1 — Basic Info',
      fs_step2_title:         'Step 2 — Formula Builder',
      fs_step3_title:         'Step 3 — Display Settings',
      fs_step4_title:         'Step 4 — Benchmarks',
      fs_step5_title:         'Step 5 — Interpretation',
      fs_ratio_name_en:       'Ratio Name (EN)',
      fs_ratio_name_ar:       'Ratio Name (AR)',
      fs_description:         'Description / tooltip text',
      fs_section:             'Section',
      fs_numerator:           'Numerator',
      fs_denominator:         'Denominator',
      fs_add_component:       'Add component',
      fs_preview:             'Preview',
      fs_result:              'Result',
      fs_zero_warning:        'Denominator evaluates to zero. The result will be undefined.',
      fs_chart_type:          'Chart Type',
      fs_chart_gauge:         'Gauge',
      fs_chart_bar:           'Progress Bar',
      fs_chart_donut:         'Donut',
      fs_chart_sparkline:     'Sparkline',
      fs_chart_number:        'Number Only',
      fs_result_format:       'Result Format',
      fs_format_number:       'Number (2 decimals)',
      fs_format_percentage:   'Percentage %',
      fs_format_multiplier:   'Multiplier ×',
      fs_benchmark_helper:    'Set three levels. The first matching range determines the card color.',
      fs_interpretation_label:'Interpretation text',
      fs_interpretation_hint: 'Use ',
      fs_interpretation_hint2:' to insert the calculated result dynamically.',
      // Misc
      outstanding_label: 'Outstanding',
      total_label:       'Total',
    },
    ar: {
      // Sidebar sections
      overview:        'نظرة عامة',
      finance:         'المالية',
      inventory:       'المخزون',
      sales:           'المبيعات',
      human_resources: 'الموارد البشرية',
      manufacturing:   'التصنيع',

      // Sidebar nav items
      dashboard:   'لوحة التحكم',
      invoices:    'الفواتير',
      bills:       'مستحقات الموردين',
      banks:       'البنوك',
      assets:      'الأصول',
      expenses:    'المصروفات',
      analytic:    'التحليلي',
      financial_statements: 'القوائم المالية',
      stock:       'المخزن',
      movements:   'حركات المخزون',
      valuation:   'التقييم',
      pipeline:    'خط المبيعات',
      orders:      'الطلبات',
      attendance:  'الحضور',
      leave:       'الإجازات',
      production:  'الإنتاج',

      // Top bar / common buttons
      refresh:      'تحديث',
      logout:       'تسجيل الخروج',
      manual:       'يدوي',
      min_5:        '5 دقائق',
      min_15:       '15 دقيقة',
      min_30:       '30 دقيقة',
      theme:        'السمة',
      color_theme:  'سمة الألوان',
      company:      'الشركة',
      export_pdf:   'PDF',
      export_excel: 'Excel',
      apply:        'تطبيق',
      filter:       'فلتر',
      clear_filters: 'مسح الفلاتر',
      clear_all:    'مسح الكل',
      search:       'بحث',
      period:       'الفترة',
      from:         'من',
      to:           'إلى',
      show_amounts_in: 'عرض المبالغ بـ',
      compare_last_year: 'مقارنة بنفس الفترة من السنة الماضية',
      overview_period: 'فترة النظرة العامة',

      // KPI cards
      total_invoices:    'إجمالي الفواتير',
      total_bills:       'إجمالي المستحقات',
      total_amount:      'إجمالي المبلغ',
      paid:              'مدفوع',
      outstanding:       'المستحق',
      fully_settled:     'مسدد بالكامل',
      awaiting_payment:  'في انتظار الدفع',

      // Payment status
      payment_status:           'حالة الدفع',
      payment_status_dist:      'توزيع حالة الدفع',
      unpaid:                   'غير مدفوع',
      partial:                  'مدفوع جزئياً',
      reversed:                 'ملغي',
      overdue:                  'متأخر',
      on_time:                  'في الموعد',
      no_overdue:               'لا يوجد تأخير',

      // Aging
      invoice_aging:      'تقادم الفواتير',
      bill_aging:         'تقادم المستحقات',
      aging_distribution: 'توزيع التقادم',
      period_days:        'الفترة (أيام)',

      // Periods
      today:         'اليوم',
      yesterday:     'أمس',
      last_7_days:   'آخر 7 أيام',
      this_month:    'هذا الشهر',
      last_month:    'الشهر الماضي',
      last_30_days:  'آخر 30 يوم',
      this_quarter:  'هذا الربع',
      last_quarter:  'الربع الماضي',
      last_6_months: 'آخر 6 أشهر',
      last_90_days:  'آخر 90 يوم',
      this_year:     'هذه السنة',
      ytd:           'منذ بداية السنة',
      last_year:     'السنة الماضية',
      last_2_years:  'آخر سنتين',
      last_365_days: 'آخر 365 يوم',
      all_time:      'كل الوقت',
      custom:        'مخصص',

      // Charts and sections
      collection_rate:      'نظرة عامة على معدل التحصيل',
      invoice_trend:        'اتجاه الفواتير',
      bill_trend:           'اتجاه المستحقات',
      tax_summary:          'ملخص الضرائب',
      total_untaxed:        'الإجمالي قبل الضريبة',
      total_with_tax:       'الإجمالي شاملاً الضريبة',
      vat_collected:        'ضريبة القيمة المضافة المحصلة',
      vat_paid:             'ضريبة القيمة المضافة المدفوعة',
      cash_flow_forecast:   'توقعات التدفق النقدي',
      based_on_today:       'بناءً على اليوم — غير متأثر بفلتر الفترة',
      next_30_days:         'الـ 30 يوم القادمة',
      total_expected:       'الإجمالي المتوقع',
      top_5_overdue:        'أعلى 5 متأخرين',
      top_5_most_profitable: 'أعلى 5 الأكثر ربحية',
      top_5_least_profitable: 'أقل 5 ربحية',

      // Tables
      invoice_num:    'الرقم',
      bill_num:       'الرقم',
      customer:       'العميل',
      vendor:         'المورد',
      issue_date:     'التاريخ',
      due_date:       'تاريخ الاستحقاق',
      amount:         'المبلغ',
      untaxed:        'قبل الضريبة',
      tax:            'الضريبة',
      status:         'الحالة',
      payment:        'الدفع',

      // Assets
      total_assets:           'إجمالي الأصول',
      acquisition_cost:       'تكلفة الاقتناء',
      net_book_value:         'صافي القيمة الدفترية',
      accumulated_dep:        'الإهلاك المتراكم',
      depreciation_this_year: 'إهلاك هذه السنة',
      fully_depreciated:      'مكتمل الإهلاك',
      asset_name:             'اسم الأصل',
      asset_model:            'نموذج الأصل',
      asset_account:          'الحساب',
      acquisition_date:       'تاريخ الاقتناء',
      original_value:         'القيمة الأصلية',
      net_value:              'صافي القيمة',
      assets_by_category:     'الأصول حسب الفئة',
      net_book_value_by_cat:  'صافي القيمة الدفترية حسب الفئة',

      // Analytic
      cost_centers:            'مراكز التكلفة',
      total_revenue:           'إجمالي الإيرادات',
      total_costs:             'إجمالي التكاليف',
      net_pl:                  'صافي الربح / الخسارة',
      account_view:            'عرض الحسابات',
      pl_accounts:             'حسابات الأرباح والخسائر',
      balance_sheet:           'حسابات الميزانية',
      all_accounts:            'كل الحسابات',
      cost_center_dist:        'توزيع مراكز التكلفة',
      revenue_vs_cost:         'الإيرادات مقابل التكاليف لكل مركز',
      profitability_map:       'خريطة الربحية',
      revenue:                 'الإيرادات',
      cost:                    'التكاليف',
      net:                     'الصافي',
      margin_pct:              'نسبة الهامش',

      // Banks
      bank_accounts:    'الحسابات البنكية',
      cash_balance:     'الرصيد النقدي',
      reconciled:       'مُسوّى',
      unreconciled:     'غير مسوّى',

      // Dashboard
      welcome:                'مرحباً',
      quick_stats:            'إحصاءات سريعة',
      module_overview:        'نظرة عامة على الوحدات',
      unpaid_invoices:        'فواتير غير مدفوعة',
      open_sales_orders:      'طلبات مبيعات مفتوحة',
      active_opportunities:   'الفرص النشطة',
      stock_products:         'منتجات المخزون',
      pending_leaves:         'طلبات إجازة معلقة',
      active_employees:       'الموظفون النشطون',
      production_in_progress: 'الإنتاج قيد التنفيذ',
      pending_expenses:       'المصروفات المعلقة',
      monthly_revenue_6:      'الإيرادات الشهرية (آخر 6 أشهر)',
      invoice_payment_status: 'حالة دفع الفواتير',
      quick_access:           'الوصول السريع',
      sales_orders:           'طلبات المبيعات',
      value_suffix:           'القيمة',
      this_month_suffix:      'هذا الشهر',

      // Inventory
      total_products:   'إجمالي المنتجات',
      total_value:      'إجمالي القيمة',
      low_stock:        'مخزون منخفض',
      out_of_stock:     'نفد المخزون',
      stock_movements:  'حركات المخزون',
      product:          'المنتج',
      quantity:         'الكمية',
      location:         'الموقع',

      // Sales
      total_orders:     'إجمالي الطلبات',
      total_sales:      'إجمالي المبيعات',
      quotations:       'عروض الأسعار',
      pipeline_value:   'قيمة خط المبيعات',
      order_number:     'رقم الطلب',
      salesperson:      'مندوب المبيعات',

      // HR
      total_employees:  'إجمالي الموظفين',
      present:          'حاضر',
      absent:           'غائب',
      on_leave:         'في إجازة',
      employee:         'الموظف',
      check_in:         'تسجيل الدخول',
      check_out:        'تسجيل الخروج',
      hours:            'الساعات',
      leave_type:       'نوع الإجازة',
      duration:         'المدة',

      // Manufacturing
      total_orders_mfg: 'أوامر التصنيع',
      in_progress:      'قيد التنفيذ',
      done:             'مكتمل',
      planned:          'مخطط',
      reference:        'المرجع',

      // Login
      login_title:      'تسجيل الدخول إلى Olens',
      login_subtitle:   'اربط حسابك في Odoo',
      odoo_url:         'رابط Odoo',
      database:         'قاعدة البيانات',
      username:         'اسم المستخدم',
      api_key:          'مفتاح API / كلمة المرور',
      sign_in:          'تسجيل الدخول',

      // Expenses / Banks
      total_expenses:        'إجمالي المصروفات',
      draft:                 'مسودة',
      reported:              'مُبلَّغ عنه',
      approved_done:         'معتمد / منجز',
      bank_cash_accounts:    'الحسابات البنكية / النقدية',
      statement_lines:       'بنود كشف الحساب',
      recent_transactions:   'المعاملات الأخيرة',
      in_payment:            'قيد الدفع',
      filtered_fully_dep:    'مفلتر: مكتمل الإهلاك',
      description:           'الوصف',
      account:               'الحساب',
      start_date:            'تاريخ البدء',
      initial_amount:        'المبلغ الأولي',
      remaining:             'المتبقي',
      recognised:            'المعترف به',
      total_def_expenses:    'إجمالي المصروفات المؤجلة',
      total_def_revenue:     'إجمالي الإيرادات المؤجلة',
      no_invoices_found:     'لا توجد فواتير',
      no_bills_found:        'لا توجد مستحقات',
      no_records_found:      'لا توجد سجلات',
      no_data_to_chart:      'لا توجد بيانات للرسم',
      no_analytic_data:      'لا توجد بيانات تحليلية',
      // Additional HR keys
      total_records:         'إجمالي السجلات',
      total_hours:           'إجمالي الساعات',
      present_today:         'الحاضرون اليوم',
      avg_hours_session:     'متوسط ساعات الجلسة',
      total_requests:        'إجمالي الطلبات',
      pending_approval:      'بانتظار الموافقة',
      approved_days:         'الأيام المعتمدة',
      refused:               'مرفوض',
      days:                  'أيام',
      leave_status:          'حالة الإجازة',
      active:                'نشط',
      full_day:              'يوم كامل',
      half_day:              'نصف يوم',
      short:                 'قصير',
      pending:               'معلق',
      second_approval:       'الموافقة الثانية',
      approved:              'معتمد',
      still_in:              'لا يزال داخل العمل',
      no_attendance_records: 'لا توجد سجلات حضور',
      no_leave_requests:     'لا توجد طلبات إجازة',
      // Additional Inventory keys
      stock_lines:           'بنود المخزون',
      total_stock_value:     'إجمالي قيمة المخزون',
      total_qty:             'إجمالي الكمية',
      zero_stock_lines:      'بنود بمخزون صفري',
      reserved:              'محجوز',
      available:             'متاح',
      top_10_by_value:       'أعلى 10 حسب القيمة',
      total_moves:           'إجمالي الحركات',
      unit_cost:             'تكلفة الوحدة',
      valuation_layers:      'طبقات التقييم',
      total_quantity:        'إجمالي الكمية',
      qty:                   'الكمية',
      no_stock_data:         'لا توجد بيانات مخزون',
      no_movements:          'لا توجد حركات',
      no_valuation_data:     'لا توجد بيانات تقييم',
      // Additional Sales keys
      confirmed:             'مؤكد',
      invoice:               'فاتورة',
      monthly_revenue:       'الإيرادات الشهرية',
      opportunities:         'الفرص',
      expected_revenue:      'الإيرادات المتوقعة',
      stages:                'المراحل',
      opportunity:           'الفرصة',
      stage:                 'المرحلة',
      expected_rev:          'الإيرادات المتوقعة',
      probability:           'الاحتمالية',
      deadline:              'الموعد النهائي',
      revenue_by_stage:      'الإيرادات حسب المرحلة',
      invoiced:              'مفوتر',
      to_invoice:            'للفوترة',
      nothing:               'لا شيء',
      sent:                  'مُرسَل',
      no_orders_found:       'لا توجد طلبات',
      no_opportunities_found: 'لا توجد فرص',
      // Additional Manufacturing keys
      qty_produced:          'الكمية المنتجة',
      planned_start:         'بداية مخططة',
      planned_end:           'نهاية مخططة',
      status_distribution:   'توزيع الحالة',
      summary:               'الملخص',
      total_qty_produced:    'إجمالي الكمية المنتجة',
      to_close:              'للإغلاق',
      cancelled:             'ملغي',
      no_mo_found:           'لا توجد أوامر تصنيع',
      // Additional Login keys
      odoo_analytics_platform: 'منصة تحليلات Odoo',
      connect_to_odoo:       'اتصال بـ Odoo',
      api_key_help:          'في Odoo: الإعدادات ← فني ← مفاتيح API ← إنشاء',
      secure_xmlrpc:         'اتصال XML-RPC آمن',
      // Misc
      // Financial Statements
      fs_pnl:               'الأرباح والخسائر',
      fs_pnl_full:          'قائمة الدخل',
      fs_balance_sheet:     'الميزانية العمومية',
      fs_trial_balance:     'ميزان المراجعة',
      fs_financial_ratios:  'النسب المالية',
      fs_total_revenue:     'إجمالي الإيرادات',
      fs_gross_profit:      'الربح الإجمالي',
      fs_operating_profit:  'الربح التشغيلي',
      fs_net_profit:        'صافي الربح',
      fs_gross_margin:      'هامش الربح الإجمالي %',
      fs_net_margin:        'هامش الربح الصافي %',
      fs_total_assets:      'إجمالي الأصول',
      fs_total_liabilities: 'إجمالي الالتزامات',
      fs_total_equity:      'إجمالي حقوق الملكية',
      fs_current_ratio:     'النسبة الجارية',
      fs_debt_equity:       'الدين إلى حقوق الملكية',
      fs_working_capital:   'رأس المال العامل',
      fs_total_debits:      'إجمالي المدين',
      fs_total_credits:     'إجمالي الدائن',
      fs_difference:        'الفرق',
      fs_total_accounts:    'إجمالي الحسابات',
      fs_assets:            'الأصول',
      fs_liabilities_equity: 'الالتزامات وحقوق الملكية',
      fs_current_assets:    'الأصول المتداولة',
      fs_non_current_assets: 'الأصول غير المتداولة',
      fs_current_liabilities: 'الالتزامات المتداولة',
      fs_non_current_liabilities: 'الالتزامات غير المتداولة',
      fs_equity:            'حقوق الملكية',
      fs_revenue:           'الإيرادات',
      fs_cost_of_revenue:   'تكلفة الإيرادات',
      fs_operating_expenses: 'المصروفات التشغيلية',
      fs_other_income_expenses: 'الإيرادات/المصروفات الأخرى',
      fs_liquidity_ratios:  'نسب السيولة',
      fs_profitability_ratios: 'نسب الربحية',
      fs_leverage_ratios:   'نسب الرافعة المالية',
      fs_efficiency_ratios: 'نسب الكفاءة',
      fs_balanced:          'متوازن',
      fs_unbalanced:        'غير متوازن',
      fs_account_code:      'رمز الحساب',
      fs_account_name:      'اسم الحساب',
      fs_account_type:      'النوع',
      fs_opening_debit:     'مدين افتتاحي',
      fs_opening_credit:    'دائن افتتاحي',
      fs_movement_debit:    'مدين الفترة',
      fs_movement_credit:   'دائن الفترة',
      fs_closing_debit:     'مدين ختامي',
      fs_closing_credit:    'دائن ختامي',
      fs_account:           'الحساب',
      fs_current_period:    'الفترة الحالية',
      fs_vs_last_year:      'مقارنة بالعام الماضي',
      fs_change_pct:        'نسبة التغير %',
      fs_pct_of_revenue:    '% من الإيرادات',
      fs_last_year:         'العام الماضي',
      fs_grand_total:       'الإجمالي العام',
      fs_balance_check:     'فحص التوازن',
      fs_formula:           'الصيغة',
      fs_benchmark:         'المعيار',
      fs_interpretation:    'التفسير',
      fs_values:            'القيم',
      fs_q1: 'الربع 1', fs_q2: 'الربع 2', fs_q3: 'الربع 3', fs_q4: 'الربع 4',
      // Account Mapping Settings drawer
      fs_settings:           'الإعدادات',
      fs_account_mapping_title: 'إعدادات ربط الحسابات',
      fs_inventory_accounts: 'حسابات المخزون',
      fs_inventory_helper:   'اختر حسابات الأصول المتداولة التي تمثل المخزون.',
      fs_cash_accounts:      'حسابات النقد فقط (باستثناء البنك)',
      fs_cash_helper:        'سيتم اعتبار الحسابات النقدية المتبقية بنوكاً.',
      fs_auto_detected:      'تم اكتشافها تلقائياً من أنواع حسابات أودو',
      fs_auto_detected_note: 'يتبع تصنيف الالتزامات نوع الحساب في أودو — غير قابل للتعديل.',
      fs_short_term_liab:    'الالتزامات قصيرة الأجل',
      fs_long_term_liab:     'الالتزامات طويلة الأجل',
      fs_demo_mapping_note:  'في وضع العرض التجريبي، يستخدم الربط بيانات نموذجية.',
      fs_mapping_warning:    'يرجى تكوين ربط الحسابات لحساب النسب المالية بدقة.',
      fs_configure_now:      'تكوين الآن',
      fs_save:               'حفظ',
      cancel:                'إلغاء',
      optional:              'اختياري',
      // Custom Ratio Builder
      fs_build_custom_ratio:  'إنشاء نسبة مخصصة',
      fs_edit_custom_ratio:   'تعديل النسبة المخصصة',
      fs_custom_badge:        'مخصصة',
      fs_custom_ratios:       'النسب المخصصة',
      fs_step_basic:          'أساسي',
      fs_step_formula:        'الصيغة',
      fs_step_display:        'العرض',
      fs_step_benchmarks:     'المعايير',
      fs_step_interpretation: 'التفسير',
      fs_step1_title:         'الخطوة 1 — معلومات أساسية',
      fs_step2_title:         'الخطوة 2 — بناء الصيغة',
      fs_step3_title:         'الخطوة 3 — إعدادات العرض',
      fs_step4_title:         'الخطوة 4 — المعايير',
      fs_step5_title:         'الخطوة 5 — التفسير',
      fs_ratio_name_en:       'اسم النسبة (إنجليزي)',
      fs_ratio_name_ar:       'اسم النسبة (عربي)',
      fs_description:         'الوصف / نص التلميح',
      fs_section:             'القسم',
      fs_numerator:           'البسط',
      fs_denominator:         'المقام',
      fs_add_component:       'إضافة عنصر',
      fs_preview:             'معاينة',
      fs_result:              'النتيجة',
      fs_zero_warning:        'المقام يساوي صفراً. ستكون النتيجة غير معرَّفة.',
      fs_chart_type:          'نوع الرسم',
      fs_chart_gauge:         'مقياس',
      fs_chart_bar:           'شريط تقدم',
      fs_chart_donut:         'دائرة مجوفة',
      fs_chart_sparkline:     'خط بياني صغير',
      fs_chart_number:        'رقم فقط',
      fs_result_format:       'تنسيق النتيجة',
      fs_format_number:       'رقم (منزلتان عشريتان)',
      fs_format_percentage:   'نسبة مئوية %',
      fs_format_multiplier:   'مضاعف ×',
      fs_benchmark_helper:    'حدد ثلاثة مستويات. أول نطاق مطابق يحدد لون البطاقة.',
      fs_interpretation_label:'نص التفسير',
      fs_interpretation_hint: 'استخدم ',
      fs_interpretation_hint2:' لإدراج النتيجة المحسوبة ديناميكياً.',
      // Misc
      outstanding_label: 'المستحق',
      total_label:       'الإجمالي',
    },
  };

  function getSaved() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return (v === 'ar' || v === 'en') ? v : null;
    } catch (e) { return null; }
  }

  function save(lang) {
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {}
  }

  // Translate a single key. Returns the key itself if missing so the
  // bug is visible in the UI rather than a blank space.
  function t(key, lang) {
    var L = lang || current();
    var dict = translations[L] || translations.en;
    return dict[key] != null ? dict[key] : key;
  }

  function current() {
    return document.documentElement.lang === 'ar' ? 'ar' : 'en';
  }

  // Walk the DOM and replace text on every [data-i18n] element.
  // data-i18n-attr="placeholder,title" lets a node translate attributes
  // too — useful for inputs and buttons whose label lives in `title`.
  function applyTranslations(lang) {
    var dict = translations[lang] || translations.en;
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      if (dict[key] != null) {
        // Preserve any leading <i> icon — only swap the trailing text node.
        var icon = el.querySelector(':scope > i:first-child');
        if (icon && el.children.length === 1) {
          // Keep the icon, replace everything after it with new text.
          while (icon.nextSibling) icon.nextSibling.remove();
          icon.insertAdjacentText('afterend', ' ' + dict[key]);
        } else if (el.children.length === 0) {
          el.textContent = dict[key];
        } else {
          // Mixed-content fallback: just rewrite first text node.
          var t = Array.from(el.childNodes).find(function (n) {
            return n.nodeType === 3;
          });
          if (t) t.nodeValue = dict[key];
          else el.textContent = dict[key];
        }
      }
    });
    // Translate attribute values for nodes that opt-in.
    document.querySelectorAll('[data-i18n-attr]').forEach(function (el) {
      el.getAttribute('data-i18n-attr').split(',').forEach(function (pair) {
        pair = pair.trim();
        if (!pair) return;
        var bits = pair.split(':');
        var attr = bits[0].trim();
        var key  = (bits[1] || el.getAttribute('data-i18n') || '').trim();
        if (key && dict[key] != null) el.setAttribute(attr, dict[key]);
      });
    });
    // Translate <option> elements whose value matches a key.
    document.querySelectorAll('select[data-i18n-options]').forEach(function (sel) {
      Array.from(sel.options).forEach(function (opt) {
        var key = opt.getAttribute('data-i18n') || opt.value;
        if (key && dict[key] != null) opt.textContent = dict[key];
      });
    });
  }

  function set(lang) {
    if (lang !== 'ar' && lang !== 'en') lang = 'en';
    save(lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = (lang === 'ar') ? 'rtl' : 'ltr';
    document.documentElement.setAttribute('data-lang', lang);
    applyTranslations(lang);
    // Buttons in the switcher show active state.
    document.querySelectorAll('.lang-btn').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-lang') === lang);
      b.setAttribute('aria-pressed', b.getAttribute('data-lang') === lang ? 'true' : 'false');
    });
    // Chart/dataset consumers subscribe to this and rebuild labels.
    try {
      document.dispatchEvent(new CustomEvent('olens:language-change',
        { detail: { lang: lang } }));
    } catch (e) {}
  }

  window.olensI18n = {
    t: t,
    set: set,
    current: current,
    translations: translations,
    apply: function () { applyTranslations(current()); },
  };

  // Apply on first DOM-ready so server-rendered defaults get translated.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      set(getSaved() || current());
    });
  } else {
    set(getSaved() || current());
  }
})();
