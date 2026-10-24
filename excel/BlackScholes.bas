Attribute VB_Name = "BlackScholes"
' Black-Scholes-Merton worksheet functions.
'
' Use them straight in cells, e.g.
'   =BS_PRICE(S, K, T, r, q, vol, "C")
'   =BS_DELTA(B2, C2, D2, $H$1, $H$2, E2, F2)
' CallPut is "C" or "P". T in years, rates and vol as decimals.
' Same conventions as riskengine/pricing.py: vega per vol point,
' theta per calendar day, rho per 1% rate move.
'
' NormCDF is written out (Hart / West double precision algorithm) instead
' of using WorksheetFunction.Norm_S_Dist so the module also runs in
' LibreOffice and in older Excel versions.
Option Explicit

Private Const PI As Double = 3.14159265358979

Public Function NormPDF(ByVal x As Double) As Double
    NormPDF = Exp(-0.5 * x * x) / Sqr(2 * PI)
End Function

Public Function NormCDF(ByVal x As Double) As Double
    Dim xa As Double, c As Double, e As Double, b As Double
    xa = Abs(x)
    If xa > 37 Then
        c = 0
    Else
        e = Exp(-xa * xa / 2)
        If xa < 7.07106781186547 Then
            b = 3.52624965998911E-02 * xa + 0.700383064443688
            b = b * xa + 6.37396220353165
            b = b * xa + 33.912866078383
            b = b * xa + 112.079291497871
            b = b * xa + 221.213596169931
            b = b * xa + 220.206867912376
            c = e * b
            b = 8.83883476483184E-02 * xa + 1.75566716318264
            b = b * xa + 16.064177579207
            b = b * xa + 86.7807322029461
            b = b * xa + 296.564248779674
            b = b * xa + 637.333633378831
            b = b * xa + 793.826512519948
            b = b * xa + 440.413735824752
            c = c / b
        Else
            b = xa + 0.65
            b = xa + 4 / b
            b = xa + 3 / b
            b = xa + 2 / b
            b = xa + 1 / b
            c = e / b / 2.506628274631
        End If
    End If
    If x > 0 Then
        NormCDF = 1 - c
    Else
        NormCDF = c
    End If
End Function

Private Function IsCall(ByVal CallPut As String) As Boolean
    Select Case UCase(Left(Trim(CallPut), 1))
        Case "C"
            IsCall = True
        Case "P"
            IsCall = False
        Case Else
            Err.Raise 5, "BlackScholes", "CallPut must be C or P"
    End Select
End Function

Private Sub D1D2(ByVal S As Double, ByVal K As Double, ByVal T As Double, ByVal r As Double, _
                 ByVal q As Double, ByVal vol As Double, ByRef d1 As Double, ByRef d2 As Double)
    d1 = (Log(S / K) + (r - q + 0.5 * vol * vol) * T) / (vol * Sqr(T))
    d2 = d1 - vol * Sqr(T)
End Sub

Public Function BS_PRICE(ByVal S As Double, ByVal K As Double, ByVal T As Double, ByVal r As Double, _
                         ByVal q As Double, ByVal vol As Double, ByVal CallPut As String) As Double
    Dim d1 As Double, d2 As Double
    If T <= 0 Then
        If IsCall(CallPut) Then
            BS_PRICE = IIf(S > K, S - K, 0)
        Else
            BS_PRICE = IIf(K > S, K - S, 0)
        End If
        Exit Function
    End If
    D1D2 S, K, T, r, q, vol, d1, d2
    If IsCall(CallPut) Then
        BS_PRICE = S * Exp(-q * T) * NormCDF(d1) - K * Exp(-r * T) * NormCDF(d2)
    Else
        BS_PRICE = K * Exp(-r * T) * NormCDF(-d2) - S * Exp(-q * T) * NormCDF(-d1)
    End If
End Function

Public Function BS_DELTA(ByVal S As Double, ByVal K As Double, ByVal T As Double, ByVal r As Double, _
                         ByVal q As Double, ByVal vol As Double, ByVal CallPut As String) As Double
    Dim d1 As Double, d2 As Double
    If T <= 0 Then
        If IsCall(CallPut) Then
            BS_DELTA = IIf(S > K, 1, 0)
        Else
            BS_DELTA = IIf(K > S, -1, 0)
        End If
        Exit Function
    End If
    D1D2 S, K, T, r, q, vol, d1, d2
    If IsCall(CallPut) Then
        BS_DELTA = Exp(-q * T) * NormCDF(d1)
    Else
        BS_DELTA = Exp(-q * T) * (NormCDF(d1) - 1)
    End If
End Function

Public Function BS_GAMMA(ByVal S As Double, ByVal K As Double, ByVal T As Double, ByVal r As Double, _
                         ByVal q As Double, ByVal vol As Double) As Double
    Dim d1 As Double, d2 As Double
    If T <= 0 Then Exit Function
    D1D2 S, K, T, r, q, vol, d1, d2
    BS_GAMMA = Exp(-q * T) * NormPDF(d1) / (S * vol * Sqr(T))
End Function

Public Function BS_VEGA(ByVal S As Double, ByVal K As Double, ByVal T As Double, ByVal r As Double, _
                        ByVal q As Double, ByVal vol As Double) As Double
    Dim d1 As Double, d2 As Double
    If T <= 0 Then Exit Function
    D1D2 S, K, T, r, q, vol, d1, d2
    BS_VEGA = S * Exp(-q * T) * NormPDF(d1) * Sqr(T) / 100
End Function

Public Function BS_THETA(ByVal S As Double, ByVal K As Double, ByVal T As Double, ByVal r As Double, _
                         ByVal q As Double, ByVal vol As Double, ByVal CallPut As String) As Double
    Dim d1 As Double, d2 As Double, common As Double
    If T <= 0 Then Exit Function
    D1D2 S, K, T, r, q, vol, d1, d2
    common = -S * Exp(-q * T) * NormPDF(d1) * vol / (2 * Sqr(T))
    If IsCall(CallPut) Then
        BS_THETA = (common - r * K * Exp(-r * T) * NormCDF(d2) + q * S * Exp(-q * T) * NormCDF(d1)) / 365
    Else
        BS_THETA = (common + r * K * Exp(-r * T) * NormCDF(-d2) - q * S * Exp(-q * T) * NormCDF(-d1)) / 365
    End If
End Function

' Implied vol by bisection, robust rather than fast. Returns -1 if the
' price is outside what any vol between 0.1% and 500% can produce.
' Deep in the money options close to expiry are almost pure intrinsic, so
' many vols give the same price and the answer is not meaningful there.
' Use out of the money quotes for implied vols.
Public Function BS_IMPLIED_VOL(ByVal Price As Double, ByVal S As Double, ByVal K As Double, ByVal T As Double, _
                               ByVal r As Double, ByVal q As Double, ByVal CallPut As String) As Double
    Dim lo As Double, hi As Double, mid As Double, i As Integer
    lo = 0.001: hi = 5
    If BS_PRICE(S, K, T, r, q, lo, CallPut) > Price Or BS_PRICE(S, K, T, r, q, hi, CallPut) < Price Then
        BS_IMPLIED_VOL = -1
        Exit Function
    End If
    For i = 1 To 100
        mid = 0.5 * (lo + hi)
        If BS_PRICE(S, K, T, r, q, mid, CallPut) > Price Then
            hi = mid
        Else
            lo = mid
        End If
        If hi - lo < 0.0000001 Then Exit For
    Next i
    BS_IMPLIED_VOL = 0.5 * (lo + hi)
End Function
