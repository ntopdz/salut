// interface.qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: mainWindow
    visible: true
    width: 1400
    height: 900
    title: "Reordering Sync Quantum Enhanced"

    // تعريف الأعمدة الكاملة لضمان المزامنة مع قاعدة البيانات
    property var allColumns: [
        "id", "year", "name", "total_seniority_days", "approved_seniority_days", "suspension_days",
        "southern_seniority_days", "southern_seniority_exhausted", "points", "current_grade",
        "current_indice", "new_grade", "new_indice", "rank_indice", "promotion_type",
        "effective_date", "new_effective_date", "financial_effect_date", "experience_years",
        "suspension_impact", "custom_text1", "custom_text2", "custom_date1", "custom_date2", "notes"
    ]
    property var columnLabels: [
        "معرف", "السنة", "الاسم", "الأقدمية الكلية", "الأقدمية المعتمدة", "الإيقاف",
        "خبرة الجنوب", "خبرة الجنوب مستنفذة", "النقاط", "الدرجة الحالية",
        "الرقم الاستدلالي للدرجة الحالية", "الدرجة الجديدة", "الرقم الاستدلالي للدرجة الجديدة",
        "الرقم الاستدلالي للرتبة", "نوع الترقية", "تاريخ السريان", "تاريخ السريان الجديد",
        "تاريخ الأثر المالي", "سنوات الخبرة", "تأثير الإيقاف", "نص مخصص 1", "نص مخصص 2",
        "تاريخ مخصص 1", "تاريخ مخصص 2", "ملاحظات"
    ]

    ColumnLayout {
        anchors.fill: parent

        // جدول العرض مع دعم التصفية والفرز المتقدم
        TableView {
            id: reorderingTable
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: ListModel { id: reorderingModel }
            columnSpacing: 2
            rowSpacing: 2
            delegate: Rectangle {
                width: reorderingTable.columnWidthProvider(column)
                height: 40
                color: row % 2 == 0 ? "#f0f0f0" : "white"
                border.color: "gray"
                Text {
                    anchors.centerIn: parent
                    text: display
                    font.pixelSize: 14
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        var colIndex = column;
                        if (colIndex === allColumns.indexOf("name")) backend.openEmployeeDialog(model.employee_id);
                        else if (colIndex === allColumns.indexOf("current_grade") || colIndex === allColumns.indexOf("new_grade")) backend.openPromotionsDialog(model.employee_id);
                        else if (colIndex === allColumns.indexOf("rank_indice")) backend.openRankDialog(model.employee_id);
                    }
                }
            }
            columnWidthProvider: function(column) {
                var widths = [80, 80, 200, 120, 120, 120, 100, 80, 80, 80, 80, 80, 80, 100, 120, 120, 120, 120, 100, 100, 100, 100, 100, 200];
                return widths[column];
            }
            Row {
                Repeater {
                    model: columnLabels
                    Label {
                        width: reorderingTable.columnWidthProvider(index)
                        height: 40
                        text: modelData
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        background: Rectangle { color: "#4682b4"; }
                        color: "white"
                        visible: backend.isColumnVisible(index)
                    }
                }
            }
            ScrollBar.vertical: ScrollBar {}
            ScrollBar.horizontal: ScrollBar {}
        }

        // شريط الأدوات مع دعم السياقات
        RowLayout {
            TextField {
                id: searchField
                placeholderText: "ابحث..."
                onTextChanged: updateTable()
            }
            ComboBox {
                id: searchFieldCombo
                model: ["الاسم", "اسم الرتبة", "اسم المؤسسة"]
                onCurrentIndexChanged: updateTable()
            }
            ComboBox {
                id: importContextCombo
                model: ["general", "HR", "Finance", "Education"]
                currentIndex: 0
                onCurrentIndexChanged: updateTable()
            }
            Button {
                text: "استيراد"
                onClicked: importDialog.open()
            }
            FileDialog {
                id: importDialog
                title: "اختر ملف للاستيراد"
                nameFilters: ["Excel files (*.xlsx *.xls)"]
                onAccepted: {
                    backend.importData(fileUrl, importContextCombo.currentText);
                }
            }
            Button {
                text: "تصدير"
                onClicked: exportDialog.open()
            }
            FileDialog {
                id: exportDialog
                title: "اختر مكان التصدير"
                fileMode: FileDialog.SaveFile
                nameFilters: ["Excel files (*.xlsx)"]
                onAccepted: backend.exportData(fileUrl)
            }
            Button {
                text: "طباعة"
                onClicked: backend.printData()
            }
            Button {
                text: "تحديث الحالة"
                onClicked: backend.syncReordering()
            }
            Button {
                text: "إدخال القواعد والدوال"
                onClicked: rulesDialog.open()
            }
            Button {
                text: "إعدادات العرض"
                onClicked: displaySettingsDialog.open()
            }
        }
    }

    // حوار تعديل بيانات الموظف
    Dialog {
        id: employeeDialog
        title: "تعديل بيانات الموظف"
        width: 400
        height: 300
        ColumnLayout {
            TextField { id: empFirstName; placeholderText: "الاسم الأول" }
            TextField { id: empLastName; placeholderText: "الاسم الأخير" }
            TextField { id: empBirthDate; placeholderText: "تاريخ الميلاد (YYYY-MM-DD)" }
            Button {
                text: "حفظ"
                onClicked: {
                    backend.updateEmployee(employeeDialog.employeeId, empFirstName.text, empLastName.text, empBirthDate.text);
                    employeeDialog.close();
                }
            }
        }
        property int employeeId: -1
    }

    // حوار إدارة الترقيات
    Dialog {
        id: promotionsDialog
        title: "إدارة الترقيات"
        width: 600
        height: 400
        ColumnLayout {
            TableView {
                id: promotionsTable
                model: ListModel { id: promotionsModel }
                delegate: Rectangle {
                    width: promotionsTable.width / 4
                    height: 40
                    Text { text: display }
                }
            }
            RowLayout {
                Button { text: "إضافة" }
                Button { text: "تعديل" }
                Button { text: "حذف" }
            }
        }
    }

    // حوار إدارة الرتب
    Dialog {
        id: rankDialog
        title: "إدارة الرتب"
        width: 600
        height: 400
        ColumnLayout {
            TableView {
                id: rankTable
                model: ListModel { id: rankModel }
                delegate: Rectangle {
                    width: rankTable.width / 4
                    height: 40
                    Text { text: display }
                }
            }
            RowLayout {
                Button { text: "إضافة" }
                Button { text: "تعديل" }
                Button { text: "حذف" }
            }
        }
    }

    // حوار إدخال القواعد والدوال مع تحليل بسيط
    Dialog {
        id: rulesDialog
        title: "إدخال القواعد والدوال"
        width: 600
        height: 500
        ColumnLayout {
            TextField { 
                id: ruleSection 
                placeholderText: "القسم (مثل row_rules أو custom_rules)" 
            }
            TextField { 
                id: ruleKey 
                placeholderText: "المفتاح (مثل infer_institution أو calc_period)" 
            }
            TextField { 
                id: ruleContext 
                placeholderText: "السياق (مثل HR، Finance، general)" 
            }
            TextArea { 
                id: ruleValue 
                placeholderText: "القاعدة أو الدالة (مثل 'repeat_text -> institution_name' أو 'custom_date2 = custom_date1 + 30')" 
            }
            Label {
                text: "أمثلة: 'repeat_text -> institution_name', 'custom_date2 = custom_date1 + 30', 'custom_text1 = first_name + \" \" + last_name'"
                wrapMode: Text.WordWrap
            }
            Label {
                id: ruleAnalysisLabel
                text: backend.analyzeRule(ruleValue.text)
                wrapMode: Text.WordWrap
                color: "blue"
            }
            Button {
                text: "حفظ"
                onClicked: {
                    var analysis = backend.analyzeRule(ruleValue.text);
                    if (analysis.includes("خطأ")) {
                        mainWindow.showAlert(analysis);
                    } else {
                        backend.saveRule(ruleSection.text, ruleKey.text, ruleValue.text, ruleContext.text);
                        console.log("حفظ: " + ruleSection.text + ", " + ruleKey.text + ", " + ruleValue.text + ", " + ruleContext.text);
                        rulesDialog.close();
                    }
                }
            }
        }
    }

    // حوار إعدادات العرض مع تحسينات
    Dialog {
        id: displaySettingsDialog
        title: "إعدادات العرض"
        width: 600
        height: 500
        ColumnLayout {
            RowLayout {
                TextField {
                    id: profileNameField
                    placeholderText: "اسم الإعداد (مثل 'عرض الترقيات')"
                }
                Button {
                    text: "حفظ الإعداد"
                    onClicked: {
                        var selectedColumns = [];
                        for (var i = 0; i < columnCheckboxes.count; i++) {
                            if (columnCheckboxes.itemAt(i).checked) {
                                selectedColumns.push(allColumns[i]);
                            }
                        }
                        if (selectedColumns.length === 0) {
                            mainWindow.showAlert("يرجى اختيار عمود واحد على الأقل!");
                            return;
                        }
                        backend.saveDisplaySettings(profileNameField.text, selectedColumns, sortColumnCombo.currentText, sortOrderCombo.currentText, importContextCombo.currentText);
                        updateTable();
                        savedProfilesCombo.model = backend.getSavedProfiles();
                    }
                }
            }
            ComboBox {
                id: savedProfilesCombo
                model: backend.getSavedProfiles()
                onCurrentTextChanged: {
                    if (currentText) {
                        var settings = backend.loadDisplaySettings(currentText);
                        for (var i = 0; i < columnCheckboxes.count; i++) {
                            columnCheckboxes.itemAt(i).checked = settings.visibleColumns.includes(allColumns[i]);
                        }
                        sortColumnCombo.currentIndex = sortColumnCombo.find(settings.sortColumn);
                        sortOrderCombo.currentIndex = settings.sortOrder === "ASC" ? 0 : 1;
                        importContextCombo.currentText = settings.context;
                        updateTable();
                    }
                }
            }
            Button {
                text: "حذف الإعداد"
                onClicked: {
                    if (savedProfilesCombo.currentText) {
                        backend.deleteDisplaySettings(savedProfilesCombo.currentText);
                        savedProfilesCombo.model = backend.getSavedProfiles();
                    }
                }
            }
            RowLayout {
                ComboBox {
                    id: sortColumnCombo
                    model: columnLabels
                }
                ComboBox {
                    id: sortOrderCombo
                    model: ["تصاعدي", "تنازلي"]
                }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    Repeater {
                        id: columnCheckboxes
                        model: columnLabels
                        CheckBox {
                            text: modelData
                            checked: true
                        }
                    }
                }
            }
        }
    }

    // حوار الاقتراحات الذكية
    Dialog {
        id: suggestionDialog
        title: "اقتراحات القواعد الذكية"
        width: 600
        height: 400
        ColumnLayout {
            ListView {
                id: suggestionList
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: ListModel { id: suggestionModel }
                delegate: RowLayout {
                    width: parent.width
                    Text { text: "المفتاح: " + model.key }
                    Text { text: "القاعدة: " + model.rule }
                    Text { text: "التكرارات: " + (model.repetitions || 1) }
                    Button {
                        text: "قبول"
                        onClicked: {
                            backend.acceptSuggestion(model.key, model.rule);
                            suggestionModel.remove(index);
                        }
                    }
                    Button {
                        text: "رفض"
                        onClicked: {
                            backend.rejectSuggestion(model.key, model.rule);
                            suggestionModel.remove(index);
                        }
                    }
                }
            }
            Button {
                text: "إغلاق"
                onClicked: suggestionDialog.close()
            }
        }
    }

    // دالة تحديث الجدول مع دعم الفرز
    function updateTable() {
        var fieldMap = {"الاسم": "name", "اسم الرتبة": "rank_indice", "اسم المؤسسة": "institution_name"};
        var searchFieldValue = fieldMap[searchFieldCombo.currentText] || "";
        var sortColumn = sortColumnCombo.currentText ? allColumns[sortColumnCombo.currentIndex] : "";
        var sortOrder = sortOrderCombo.currentText === "تصاعدي" ? "ASC" : "DESC";
        var data = backend.getReordering(searchField.text, searchFieldValue, sortColumn, sortOrder);
        reorderingModel.clear();
        for (var i = 0; i < data.length; i++) {
            reorderingModel.append(data[i]);
        }
    }

    // دالة عرض التنبيهات
    function showAlert(message) {
        alertLabel.text = message;
        alertTimer.restart();
    }

    // الاتصالات مع الخلفية
    Connections {
        target: backend
        function onTableUpdated(data) {
            reorderingModel.clear();
            for (var i = 0; i < data.length; i++) {
                reorderingModel.append(data[i]);
            }
        }
        function onEmployeeDialogRequested(employeeId) {
            employeeDialog.employeeId = employeeId;
            employeeDialog.open();
        }
        function onPromotionsDialogRequested(employeeId) { promotionsDialog.open(); }
        function onRankDialogRequested(employeeId) { rankDialog.open(); }
        function onRulesSuggested(suggestions) {
            suggestionModel.clear();
            for (var i = 0; i < suggestions.length; i++) {
                suggestionModel.append(suggestions[i]);
            }
            suggestionDialog.open();
        }
        function onAlert(message) {
            showAlert(message);
        }
    }

    // تنبيهات خفيفة
    Label {
        id: alertLabel
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 10
        text: ""
        color: "red"
        visible: text !== ""
    }
    Timer {
        id: alertTimer
        interval: 5000
        onTriggered: alertLabel.text = ""
    }

    Component.onCompleted: updateTable()
}