export type DayStatus = "not_started" | "in_progress" | "done" | "blocked";

export interface DayPlan {
  day: number;
  title: string;
  tasks: string[];
  status: DayStatus;
  notes: string;
}

export const plan: DayPlan[] = [
  {
    day: 1,
    title: "Lab Baseline & Inventory",
    tasks: [
      "Document available routers, switches, and host OS versions",
      "Verify console and SSH access to all devices",
      "Create an addressing worksheet for management interfaces"
    ],
    status: "not_started",
    notes: ""
  },
  {
    day: 2,
    title: "IPv4 Subnetting Practice",
    tasks: [
      "Solve at least 20 subnetting questions",
      "Create three /30 point-to-point links in the lab",
      "Validate routes and connectivity with ping/traceroute"
    ],
    status: "not_started",
    notes: ""
  },
  {
    day: 3,
    title: "VLANs and Trunking",
    tasks: [
      "Create VLAN 10/20/30 and assign access ports",
      "Configure 802.1Q trunk between switches",
      "Verify tagging and inter-VLAN reachability prerequisites"
    ],
    status: "not_started",
    notes: ""
  }
];
