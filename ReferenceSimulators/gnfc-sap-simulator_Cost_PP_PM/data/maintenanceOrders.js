// Mock Maintenance Order data
// Mirrors SAP PM API_MAINTENANCEORDER / A_MaintenanceOrder
// OrderType: PM01 = Corrective (breakdown), PM02 = Preventive/Planned
// Linked 1:1 to a notification via NotificationID where applicable.

const maintenanceOrders = [
  { OrderID: "30000101", NotificationID: "10000101", EquipmentID: "10001001", OrderType: "PM01", PlannedCost: 45000,  ActualCost: 52300,  Currency: "INR", BasicStartDate: "2026-04-05", BasicFinishDate: "2026-04-05", OrderStatus: "TECO" },
  { OrderID: "30000102", NotificationID: "10000102", EquipmentID: "10001001", OrderType: "PM02", PlannedCost: 18000,  ActualCost: 17200,  Currency: "INR", BasicStartDate: "2026-04-10", BasicFinishDate: "2026-04-10", OrderStatus: "TECO" },
  { OrderID: "30000103", NotificationID: "10000103", EquipmentID: "10001002", OrderType: "PM01", PlannedCost: 380000, ActualCost: 465000, Currency: "INR", BasicStartDate: "2026-05-12", BasicFinishDate: "2026-05-13", OrderStatus: "TECO" },
  { OrderID: "30000104", NotificationID: "10000104", EquipmentID: "10001003", OrderType: "PM01", PlannedCost: 120000, ActualCost: 138500, Currency: "INR", BasicStartDate: "2026-06-02", BasicFinishDate: "2026-06-02", OrderStatus: "TECO" },
  { OrderID: "30000105", NotificationID: "10000105", EquipmentID: "10001004", OrderType: "PM01", PlannedCost: 30000,  ActualCost: 28500,  Currency: "INR", BasicStartDate: "2026-04-21", BasicFinishDate: "2026-04-21", OrderStatus: "TECO" },
  { OrderID: "30000106", NotificationID: "10000106", EquipmentID: "10001005", OrderType: "PM02", PlannedCost: 250000, ActualCost: 241000, Currency: "INR", BasicStartDate: "2026-04-18", BasicFinishDate: "2026-04-19", OrderStatus: "TECO" },
  { OrderID: "30000107", NotificationID: "10000107", EquipmentID: "10001006", OrderType: "PM01", PlannedCost: 410000, ActualCost: 502000, Currency: "INR", BasicStartDate: "2026-05-28", BasicFinishDate: "2026-05-29", OrderStatus: "TECO" },
  { OrderID: "30000108", NotificationID: "10000108", EquipmentID: "10001007", OrderType: "PM01", PlannedCost: 95000,  ActualCost: 101200, Currency: "INR", BasicStartDate: "2026-06-15", BasicFinishDate: "2026-06-15", OrderStatus: "TECO" },
  { OrderID: "30000109", NotificationID: "10000109", EquipmentID: "10001008", OrderType: "PM01", PlannedCost: 150000, ActualCost: 178000, Currency: "INR", BasicStartDate: "2026-04-27", BasicFinishDate: "2026-04-28", OrderStatus: "TECO" },
  { OrderID: "30000110", NotificationID: "10000110", EquipmentID: "10001009", OrderType: "PM02", PlannedCost: 60000,  ActualCost: 57500,  Currency: "INR", BasicStartDate: "2026-05-05", BasicFinishDate: "2026-05-05", OrderStatus: "TECO" },
  { OrderID: "30000111", NotificationID: "10000111", EquipmentID: "10001010", OrderType: "PM01", PlannedCost: 320000, ActualCost: 389500, Currency: "INR", BasicStartDate: "2026-05-08", BasicFinishDate: "2026-05-09", OrderStatus: "TECO" },
  { OrderID: "30000112", NotificationID: "10000112", EquipmentID: "10001011", OrderType: "PM01", PlannedCost: 40000,  ActualCost: 43800,  Currency: "INR", BasicStartDate: "2026-04-14", BasicFinishDate: "2026-04-14", OrderStatus: "TECO" },
  { OrderID: "30000113", NotificationID: "10000113", EquipmentID: "10001012", OrderType: "PM02", PlannedCost: 85000,  ActualCost: 82300,  Currency: "INR", BasicStartDate: "2026-05-02", BasicFinishDate: "2026-05-03", OrderStatus: "TECO" },
  { OrderID: "30000114", NotificationID: "10000114", EquipmentID: "10001013", OrderType: "PM01", PlannedCost: 55000,  ActualCost: 58900,  Currency: "INR", BasicStartDate: "2026-06-08", BasicFinishDate: "2026-06-08", OrderStatus: "TECO" },
  { OrderID: "30000115", NotificationID: "10000115", EquipmentID: "10001014", OrderType: "PM01", PlannedCost: 480000, ActualCost: 610000, Currency: "INR", BasicStartDate: "2026-05-20", BasicFinishDate: "2026-05-21", OrderStatus: "TECO" },
  { OrderID: "30000116", NotificationID: "10000116", EquipmentID: "10001015", OrderType: "PM02", PlannedCost: 350000, ActualCost: 340500, Currency: "INR", BasicStartDate: "2026-06-25", BasicFinishDate: "2026-06-26", OrderStatus: "TECO" },
  { OrderID: "30000117", NotificationID: "20000101", EquipmentID: "20001001", OrderType: "PM01", PlannedCost: 275000, ActualCost: 312000, Currency: "INR", BasicStartDate: "2026-04-30", BasicFinishDate: "2026-05-01", OrderStatus: "TECO" },
  { OrderID: "30000118", NotificationID: "20000102", EquipmentID: "20001002", OrderType: "PM01", PlannedCost: 110000, ActualCost: 134500, Currency: "INR", BasicStartDate: "2026-06-20", BasicFinishDate: "2026-06-21", OrderStatus: "TECO" },
  { OrderID: "30000119", NotificationID: "20000103", EquipmentID: "20001003", OrderType: "PM02", PlannedCost: 190000, ActualCost: 185000, Currency: "INR", BasicStartDate: "2026-05-15", BasicFinishDate: "2026-05-16", OrderStatus: "TECO" },
];

module.exports = maintenanceOrders;
