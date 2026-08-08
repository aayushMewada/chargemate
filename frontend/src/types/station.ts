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
  name: string;
  address_line_1: string;
  city: string;
  state: string;
  postal_code: string;
  status: string;
  is_24_hours: boolean;
  distance_km?: number;
  charge_points: ChargePoint[];
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

export type ExternalStationResponse = {
  stations: ExternalStation[];
  source: "open_charge_map";
  bookable: false;
};
