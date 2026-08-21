import { AxiosError, AxiosHeaders } from "axios";

/** Build the AxiosError the API client would reject with for an HTTP status. */
export function httpError(status: number, detail?: string): AxiosError {
  const headers = new AxiosHeaders();
  return new AxiosError(
    `Request failed with status code ${status}`,
    "ERR_BAD_REQUEST",
    { headers },
    null,
    {
      status,
      statusText: String(status),
      headers: {},
      config: { headers },
      data: detail === undefined ? {} : { detail },
    },
  );
}
