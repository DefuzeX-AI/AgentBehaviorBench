// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "LWebSocketClientWrapper.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnWsConnectedEvent);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnWsConnectionErrorEvent, const FString&, Error);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnWsClosedEvent, int32, StatusCode, const FString&, Reason, bool, bWasClean);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnWsMessageEvent, const FString&, Message);

UCLASS(BlueprintType, Blueprintable)
class UE5PROJECT_API ULWebSocketClientWrapper : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	bool Connect(const FString& Url, const FString& Protocol);

	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	static void Close(int32 StatusCode = 1000, const FString& Reason = TEXT(""));

	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	static void SendMessage(const FString& Message);

	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	static bool IsConnected();

	UPROPERTY(BlueprintAssignable, Category = "WebSocket")
	FOnWsConnectedEvent OnConnectedEvent;

	UPROPERTY(BlueprintAssignable, Category = "WebSocket")
	FOnWsConnectionErrorEvent OnConnectionErrorEvent;

	UPROPERTY(BlueprintAssignable, Category = "WebSocket")
	FOnWsClosedEvent OnClosedEvent;

	UPROPERTY(BlueprintAssignable, Category = "WebSocket")
	FOnWsMessageEvent OnMessageEvent;

private:
	UFUNCTION()
	void HandleConnected();

	UFUNCTION()
	void HandleConnectionError(const FString& Error);

	UFUNCTION()
	void HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean);

	UFUNCTION()
	void HandleMessage(const FString& Message);
};
