// Mock Equipment Master (mirrors SAP PM API_EQUIPMENT_SRV / A_Equipment)
// FunctionalLocation follows the asset hierarchy already established:
// Plant (Bharuch/Dahej) > Unit > Equipment

const equipment = [
  { EquipmentID: "10001001", Description: "Ammonia Feed Pump",           Plant: "1001-BHR", Unit: "Ammonia (Natural Gas Route)", FunctionalLocation: "BHR-AMMNG-PUMP-101", EquipmentClass: "Pump",        Manufacturer: "KSB",       InstallDate: "2016-03-01" },
  { EquipmentID: "10001002", Description: "Ammonia Synthesis Compressor", Plant: "1001-BHR", Unit: "Ammonia (Natural Gas Route)", FunctionalLocation: "BHR-AMMNG-COMP-201", EquipmentClass: "Compressor", Manufacturer: "Elliott",   InstallDate: "2016-03-01" },
  { EquipmentID: "10001003", Description: "Primary Reformer",            Plant: "1001-BHR", Unit: "Ammonia (Natural Gas Route)", FunctionalLocation: "BHR-AMMNG-REF-301",  EquipmentClass: "Reactor",    Manufacturer: "Haldor Topsoe", InstallDate: "2016-03-01" },
  { EquipmentID: "10001004", Description: "Boiler Feed Water Pump",       Plant: "1001-BHR", Unit: "Urea",                        FunctionalLocation: "BHR-UREA-PUMP-102",  EquipmentClass: "Pump",       Manufacturer: "KSB",       InstallDate: "2015-11-15" },
  { EquipmentID: "10001005", Description: "Urea Reactor",                 Plant: "1001-BHR", Unit: "Urea",                        FunctionalLocation: "BHR-UREA-REACT-401", EquipmentClass: "Reactor",    Manufacturer: "Stamicarbon", InstallDate: "2015-11-15" },
  { EquipmentID: "10001006", Description: "CO2 Compressor",               Plant: "1001-BHR", Unit: "Urea",                        FunctionalLocation: "BHR-UREA-COMP-202",  EquipmentClass: "Compressor", Manufacturer: "Elliott",   InstallDate: "2015-11-15" },
  { EquipmentID: "10001007", Description: "Nitric Acid Absorption Column",Plant: "1001-BHR", Unit: "Concentrated Nitric Acid",    FunctionalLocation: "BHR-CNA-COL-101",    EquipmentClass: "Column",     Manufacturer: "Uhde",      InstallDate: "2010-06-01" },
  { EquipmentID: "10001008", Description: "Acetic Acid Distillation Column", Plant: "1001-BHR", Unit: "Acetic Acid",             FunctionalLocation: "BHR-AA-COL-102",     EquipmentClass: "Column",     Manufacturer: "Sulzer",    InstallDate: "2012-01-20" },
  { EquipmentID: "10001009", Description: "Methanol Reboiler",            Plant: "1001-BHR", Unit: "Methanol",                    FunctionalLocation: "BHR-MEOH-HX-301",    EquipmentClass: "Heat Exchanger", Manufacturer: "Alfa Laval", InstallDate: "2013-09-10" },
  { EquipmentID: "10001010", Description: "TDI Phosgenation Reactor",     Plant: "1001-BHR", Unit: "Toluene Di Isocyanate (Bharuch)", FunctionalLocation: "BHR-TDI-REACT-402", EquipmentClass: "Reactor",  Manufacturer: "Bayer Technology", InstallDate: "2018-05-05" },
  { EquipmentID: "10001011", Description: "Boiler 1",                     Plant: "1001-BHR", Unit: "Coal/Natural Gas Boilers",    FunctionalLocation: "BHR-BOIL-01",        EquipmentClass: "Boiler",     Manufacturer: "Thermax",   InstallDate: "2009-01-01" },
  { EquipmentID: "10001012", Description: "Boiler 2",                     Plant: "1001-BHR", Unit: "Coal/Natural Gas Boilers",    FunctionalLocation: "BHR-BOIL-02",        EquipmentClass: "Boiler",     Manufacturer: "Thermax",   InstallDate: "2009-01-01" },
  { EquipmentID: "10001013", Description: "Boiler 4",                     Plant: "1001-BHR", Unit: "Coal/Natural Gas Boilers",    FunctionalLocation: "BHR-BOIL-04",        EquipmentClass: "Boiler",     Manufacturer: "Thermax",   InstallDate: "2019-07-15" },
  { EquipmentID: "10001014", Description: "Steam Turbine 1",              Plant: "1001-BHR", Unit: "Steam Turbines",              FunctionalLocation: "BHR-TURB-01",        EquipmentClass: "Turbine",    Manufacturer: "Siemens",   InstallDate: "2011-04-01" },
  { EquipmentID: "10001015", Description: "Gas Turbine",                  Plant: "1001-BHR", Unit: "Gas Turbine",                 FunctionalLocation: "BHR-TURB-GT",        EquipmentClass: "Turbine",    Manufacturer: "GE",        InstallDate: "2014-02-01" },
  { EquipmentID: "20001001", Description: "TDI Reactor (Dahej)",          Plant: "2001-DHJ", Unit: "Toluene Di Isocyanate (Dahej)", FunctionalLocation: "DHJ-TDI-REACT-501", EquipmentClass: "Reactor",   Manufacturer: "Bayer Technology", InstallDate: "2020-08-01" },
  { EquipmentID: "20001002", Description: "Boiler (Dahej)",               Plant: "2001-DHJ", Unit: "Boiler (Dahej)",              FunctionalLocation: "DHJ-BOIL-D1",        EquipmentClass: "Boiler",     Manufacturer: "Thermax",   InstallDate: "2020-08-01" },
  { EquipmentID: "20001003", Description: "Syn Gas Generator (Dahej)",    Plant: "2001-DHJ", Unit: "Syn Gas Generator (Dahej)",   FunctionalLocation: "DHJ-SYNGEN-01",      EquipmentClass: "Gasifier",  Manufacturer: "Air Liquide", InstallDate: "2020-08-01" },
];

module.exports = equipment;
