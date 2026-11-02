// @vitest-environment jsdom
/**
 * While the server is waking up, failures from the host are retried and
 * the "waking up" state is shown; once it has answered, errors are errors.
 */

import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { describe, expect, it } from "vitest";

import { api } from "./api";
import { isServerAwake } from "./serverWake";

function reply(config: InternalAxiosRequestConfig, status: number): AxiosResponse {
  return { data: { status: "ok" }, status, statusText: "", headers: {}, config };
}

describe("waking the server", () => {
  it("retries the host's 503s while it boots, then succeeds", async () => {
    let calls = 0;
    api.defaults.adapter = async (config) => {
      calls += 1;
      if (calls <= 2) {
        const response = reply(config, 503);
        throw new AxiosError("Service Unavailable", "ERR_BAD_RESPONSE", config, null, response);
      }
      return reply(config, 200);
    };

    expect(isServerAwake()).toBe(false);
    const response = await api.get("/health");

    expect(response.status).toBe(200);
    expect(calls).toBe(3);
    expect(isServerAwake()).toBe(true);
  }, 20_000);

  it("doesn't retry once the server is awake", async () => {
    let calls = 0;
    api.defaults.adapter = async (config) => {
      calls += 1;
      const response = reply(config, 503);
      throw new AxiosError("Service Unavailable", "ERR_BAD_RESPONSE", config, null, response);
    };

    await expect(api.get("/health")).rejects.toBeInstanceOf(AxiosError);
    expect(calls).toBe(1);
  });
});
