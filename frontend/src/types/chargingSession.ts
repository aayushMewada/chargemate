export type ChargingSessionStatus = "active" | "completed" | "interrupted";

export type ChargingSession = {
  id: string;
  booking_id: string;
  charge_point_id: string;
  charge_point: {
    id: string;
    code: string;
    connector_type: string;
    power_type: string;
    max_power_kw: number;
    station: {
      id: string;
      name: string;
      city: string;
      state: string;
    };
  };
  booking_window: {
    starts_at: string;
    ends_at: string;
  };
  status: ChargingSessionStatus;
  started_at: string;
  ended_at: string | null;
  meter_start_kwh: number;
  meter_end_kwh: number | null;
  energy_consumed_kwh: number | null;
  version: number;
  created_at: string;
};

export type ChargingSessionPage = {
  charging_sessions: ChargingSession[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    pages: number;
  };
};

export type ChargingOperation = {
  booking: {
    id: string;
    status: "confirmed" | "active";
    version: number;
    starts_at: string;
    ends_at: string;
  };
  customer: {
    id: string;
    full_name: string;
    email: string;
  };
  charge_point: {
    id: string;
    code: string;
    connector_type: string;
    max_power_kw: number;
  };
  station: {
    id: string;
    name: string;
    city: string;
    state: string;
  };
  charging_session: {
    id: string;
    status: "active";
    version: number;
    started_at: string;
    meter_start_kwh: number;
  } | null;
};

export type ChargingOperationPage = {
  operations: ChargingOperation[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    pages: number;
  };
};

export type ChargingSessionResponse = {
  charging_session: ChargingSession;
};
