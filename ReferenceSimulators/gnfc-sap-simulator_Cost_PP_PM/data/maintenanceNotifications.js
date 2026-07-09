// Mock Maintenance Notification data
// Mirrors SAP PM API_MAINTNOTIFICATION_SRV / A_MaintenanceNotification
// NotificationType: M1 = Breakdown, M2 = Preventive/Planned
// Window: 2026-04-01 to 2026-06-30 (one quarter, ~2160 hours) for MTBF/MTTR calc

const notifications = [
  { NotificationID: "10000101", EquipmentID: "10001001", NotificationType: "M1", Description: "Ammonia feed pump seal leak",        MalfunctionStart: "2026-04-05T02:00:00", MalfunctionEnd: "2026-04-05T07:30:00", Priority: "High" },
  { NotificationID: "10000102", EquipmentID: "10001001", NotificationType: "M2", Description: "Scheduled pump bearing inspection",   MalfunctionStart: null, MalfunctionEnd: null, Priority: "Medium" },
  { NotificationID: "10000103", EquipmentID: "10001002", NotificationType: "M1", Description: "Synthesis compressor high vibration", MalfunctionStart: "2026-05-12T14:00:00", MalfunctionEnd: "2026-05-13T04:00:00", Priority: "Critical" },
  { NotificationID: "10000104", EquipmentID: "10001003", NotificationType: "M1", Description: "Reformer tube temperature excursion", MalfunctionStart: "2026-06-02T09:00:00", MalfunctionEnd: "2026-06-02T15:00:00", Priority: "High" },
  { NotificationID: "10000105", EquipmentID: "10001004", NotificationType: "M1", Description: "BFW pump trip on low suction pressure", MalfunctionStart: "2026-04-20T22:00:00", MalfunctionEnd: "2026-04-21T03:00:00", Priority: "Medium" },
  { NotificationID: "10000106", EquipmentID: "10001005", NotificationType: "M2", Description: "Urea reactor annual inspection",       MalfunctionStart: null, MalfunctionEnd: null, Priority: "Medium" },
  { NotificationID: "10000107", EquipmentID: "10001006", NotificationType: "M1", Description: "CO2 compressor unplanned shutdown",   MalfunctionStart: "2026-05-28T06:00:00", MalfunctionEnd: "2026-05-29T18:00:00", Priority: "Critical" },
  { NotificationID: "10000108", EquipmentID: "10001007", NotificationType: "M1", Description: "Absorption column pressure drop alarm", MalfunctionStart: "2026-06-15T11:00:00", MalfunctionEnd: "2026-06-15T16:30:00", Priority: "High" },
  { NotificationID: "10000109", EquipmentID: "10001008", NotificationType: "M1", Description: "Distillation column reboiler fouling", MalfunctionStart: "2026-04-27T00:00:00", MalfunctionEnd: "2026-04-28T08:00:00", Priority: "High" },
  { NotificationID: "10000110", EquipmentID: "10001009", NotificationType: "M2", Description: "Reboiler tube-bundle cleaning",        MalfunctionStart: null, MalfunctionEnd: null, Priority: "Low" },
  { NotificationID: "10000111", EquipmentID: "10001010", NotificationType: "M1", Description: "TDI reactor agitator motor fault",     MalfunctionStart: "2026-05-08T05:00:00", MalfunctionEnd: "2026-05-09T01:00:00", Priority: "Critical" },
  { NotificationID: "10000112", EquipmentID: "10001011", NotificationType: "M1", Description: "Boiler 1 flame failure trip",         MalfunctionStart: "2026-04-14T16:00:00", MalfunctionEnd: "2026-04-14T20:00:00", Priority: "High" },
  { NotificationID: "10000113", EquipmentID: "10001012", NotificationType: "M2", Description: "Boiler 2 statutory inspection",        MalfunctionStart: null, MalfunctionEnd: null, Priority: "Medium" },
  { NotificationID: "10000114", EquipmentID: "10001013", NotificationType: "M1", Description: "Boiler 4 feedwater control valve stuck", MalfunctionStart: "2026-06-08T03:00:00", MalfunctionEnd: "2026-06-08T09:00:00", Priority: "Medium" },
  { NotificationID: "10000115", EquipmentID: "10001014", NotificationType: "M1", Description: "Steam turbine 1 vibration trip",      MalfunctionStart: "2026-05-20T10:00:00", MalfunctionEnd: "2026-05-21T22:00:00", Priority: "Critical" },
  { NotificationID: "10000116", EquipmentID: "10001015", NotificationType: "M2", Description: "Gas turbine combustor borescope inspection", MalfunctionStart: null, MalfunctionEnd: null, Priority: "Low" },
  { NotificationID: "20000101", EquipmentID: "20001001", NotificationType: "M1", Description: "TDI reactor (Dahej) cooling water loss", MalfunctionStart: "2026-04-30T13:00:00", MalfunctionEnd: "2026-05-01T02:00:00", Priority: "Critical" },
  { NotificationID: "20000102", EquipmentID: "20001002", NotificationType: "M1", Description: "Boiler (Dahej) tube leak",             MalfunctionStart: "2026-06-20T07:00:00", MalfunctionEnd: "2026-06-21T19:00:00", Priority: "High" },
  { NotificationID: "20000103", EquipmentID: "20001003", NotificationType: "M2", Description: "Syn gas generator catalyst change-out", MalfunctionStart: null, MalfunctionEnd: null, Priority: "Medium" },
];

module.exports = notifications;
