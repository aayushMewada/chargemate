export type Coordinates = {
  latitude: number;
  longitude: number;
};

export type ChargePoint = {
  id: string;
  code: string;
  connector_type: string;
  power_type: string;
  max_power_kw: number;
  booking_fee: number;
  is_bookable: boolean;
  status: string;
  version: number;
};

export type ManagedStation = Coordinates & {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country_code: string;
  timezone: string;
  phone: string | null;
  status: string;
  is_24_hours: boolean;
  version: number;
  distance_km?: number;
  charge_points: ChargePoint[];
  created_at: string;
};

export type ExternalStation = Coordinates & {
  external_id: string;
  name: string;
  operator: string | null;
  status: string | null;
  distance_km: number | null;
  details_url: string | null;
  bookable: false;
  address: {
    line_1: string | null;
    town: string | null;
    state: string | null;
    postal_code: string | null;
    country_code: string | null;
  };
  connections: Array<{
    type: string;
    current_type: string | null;
    power_kw: number | null;
    quantity: number | null;
  }>;
};

export type StationMarker = Coordinates & {
  id: string;
  name: string;
  address: string;
  source: "chargemate" | "open_charge_map";
  bookable: boolean;
  status: string;
  distanceKm: number | null;
  connectorSummary: string;
  externalDetailsUrl: string | null;
};

export type ManagedStationResponse = {
  stations: ManagedStation[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    pages: number;
  };
};

export type ManagedStationDetailResponse = {
  station: ManagedStation;
};

export type OwnedStationResponse = ManagedStationResponse;

export type ChargePointUpdateResponse = {
  charge_point: ChargePoint;
};

export type ConnectorType =
  | "ccs_2"
  | "type_2"
  | "chademo"
  | "gb_t"
  | "bharat_dc_001";

export type StationCreateInput = Coordinates & {
  name: string;
  description: string | null;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country_code: string;
  timezone: string;
  phone: string | null;
  is_24_hours: boolean;
  charge_points: Array<{
    code: string;
    connector_type: ConnectorType;
    power_type: "ac" | "dc";
    max_power_kw: number;
    booking_fee: number;
    is_bookable: boolean;
  }>;
};

export type ExternalStationResponse = {
  stations: ExternalStation[];
  source: "open_charge_map";
  bookable: false;
};
