export interface CapacityBody {
  fabric_mode: "l3ls" | "l2ls";
  max_spines: number;
  max_leaves: number;
  max_mleafs_per_pair: number;
  spines: number;
  leaves: number;
  use_case: "datacenter" | "campus" | null;
  bb_redundancy: "mlag-peer" | "evpn-aa";
  border_redundancy: "mlag-peer" | "evpn-aa";
  bb_count: number;
  border_count: number;
  backbone_mode: "hub";
}

export interface PreviewBody {
  hostname_prefix: string;
  serial_prefix: string;
  eos_version: string;
  capacity: CapacityBody;
  mlag_pairs: boolean;
  spine_mlag: boolean;
  member_leaf_pairs: number[];
  member_leaves_per_pair: number;
  dc_count: number;
  sites: string[];
}

export interface PreviewResult {
  yaml_text: string;
  png_base64: string | null;
  summary: {
    node_count: number;
    fabric_mode: string;
    sites: string[];
    title: string;
  };
}

export interface WriteTopologyBody {
  yaml_text: string;
  stem: string;
}

export interface WriteTopologyResult {
  path: string;
  name: string;
}
